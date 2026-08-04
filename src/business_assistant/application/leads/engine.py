"""Pure deterministic answer validation, scoring, and escalation rules."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from business_assistant.domain.shared import PhoneNumber, ValidationError

from .models import (
    Answer,
    HandoffTrigger,
    MatchOperator,
    QualificationField,
    QualificationFieldType,
    QualificationSchema,
    ScoreResult,
    TriggerResult,
)


class InvalidAnswerError(ValueError):
    def __init__(self, correction: str) -> None:
        self.correction = correction
        super().__init__(correction)


def _text(value: str, field: QualificationField) -> str:
    normalized = " ".join(value.strip().split())
    validation = field.validation
    if not normalized and field.required:
        raise InvalidAnswerError(f"{field.label} is required.")
    if validation.min_length is not None and len(normalized) < validation.min_length:
        raise InvalidAnswerError(
            f"{field.label} must contain at least {validation.min_length} characters."
        )
    if validation.max_length is not None and len(normalized) > validation.max_length:
        raise InvalidAnswerError(
            f"{field.label} must contain at most {validation.max_length} characters."
        )
    if validation.pattern is not None and not re.fullmatch(validation.pattern, normalized):
        raise InvalidAnswerError(f"Enter a valid value for {field.label}.")
    return normalized


def validate_answer(field: QualificationField, raw: str) -> Answer:
    value = raw.strip()
    kind = field.field_type
    if kind in {QualificationFieldType.SHORT_TEXT, QualificationFieldType.LONG_TEXT}:
        return _text(value, field)
    if kind is QualificationFieldType.SINGLE_CHOICE:
        match = next(
            (item for item in field.validation.options if item.casefold() == value.casefold()), None
        )
        if match is None:
            raise InvalidAnswerError(f"Choose one of: {', '.join(field.validation.options)}.")
        return match
    if kind is QualificationFieldType.MULTI_CHOICE:
        supplied = {item.strip().casefold() for item in value.split(",") if item.strip()}
        selected = tuple(item for item in field.validation.options if item.casefold() in supplied)
        if not selected or len(selected) != len(supplied):
            choices = ", ".join(field.validation.options)
            raise InvalidAnswerError(f"Choose one or more comma-separated values from: {choices}.")
        return selected
    if kind is QualificationFieldType.PHONE:
        try:
            return PhoneNumber.parse(value).raw
        except ValidationError as exc:
            raise InvalidAnswerError(
                "Enter a valid phone number using digits and an optional + prefix."
            ) from exc
    if kind is QualificationFieldType.EMAIL:
        if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise InvalidAnswerError("Enter a valid email address, such as name@example.com.")
        return value.casefold()
    if kind in {QualificationFieldType.INTEGER, QualificationFieldType.DECIMAL}:
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise InvalidAnswerError(f"Enter a valid number for {field.label}.") from exc
        if not number.is_finite() or (
            kind is QualificationFieldType.INTEGER and number != number.to_integral()
        ):
            raise InvalidAnswerError(f"Enter a whole number for {field.label}.")
        if field.validation.minimum is not None and number < field.validation.minimum:
            raise InvalidAnswerError(f"{field.label} must be at least {field.validation.minimum}.")
        if field.validation.maximum is not None and number > field.validation.maximum:
            raise InvalidAnswerError(f"{field.label} must be at most {field.validation.maximum}.")
        return int(number) if kind is QualificationFieldType.INTEGER else number
    if kind is QualificationFieldType.BOOLEAN:
        if value.casefold() in {"yes", "true", "1"}:
            return True
        if value.casefold() in {"no", "false", "0"}:
            return False
        raise InvalidAnswerError("Answer yes or no.")
    if kind is QualificationFieldType.DATE:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise InvalidAnswerError("Enter a date in YYYY-MM-DD format.") from exc
    raise AssertionError("Unsupported qualification field type")


def _matches(actual: Answer, operator: MatchOperator, expected: object) -> bool:
    if operator is MatchOperator.EQUALS:
        return actual == expected
    if operator is MatchOperator.CONTAINS:
        needle = str(expected).casefold()
        if isinstance(actual, tuple):
            return any(needle == item.casefold() for item in actual)
        return needle in str(actual).casefold()
    left, right = Decimal(str(actual)), Decimal(str(expected))
    return left >= right if operator is MatchOperator.GREATER_THAN_OR_EQUAL else left <= right


def score_answers(schema: QualificationSchema, answers: dict[str, Answer]) -> ScoreResult:
    total = 0
    matched: list[str] = []
    for field in schema.fields:
        if field.key not in answers:
            continue
        for rule in field.score_rules:
            if _matches(answers[field.key], rule.operator, rule.expected):
                total += rule.points
                matched.append(rule.code)
    score = max(0, min(100, total))
    grade = max(
        (band for band in schema.grade_bands if score >= band.minimum_score),
        key=lambda band: band.minimum_score,
    ).grade
    return ScoreResult(score, grade, tuple(matched))


def detect_handoff(schema: QualificationSchema, answers: dict[str, Answer]) -> TriggerResult | None:
    matches: list[HandoffTrigger] = []
    for field in schema.fields:
        if field.key not in answers:
            continue
        matches.extend(
            trigger
            for trigger in field.handoff_triggers
            if _matches(answers[field.key], trigger.operator, trigger.expected)
        )
    if not matches:
        return None
    rank = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
    winner = max(matches, key=lambda item: (rank[item.priority], item.code))
    return TriggerResult(
        winner.reason_code,
        winner.priority,
        tuple(sorted(item.code for item in matches)),
    )


def next_missing_field(
    schema: QualificationSchema, answers: dict[str, Answer]
) -> QualificationField | None:
    return next(
        (field for field in schema.fields if field.required and field.key not in answers), None
    )
