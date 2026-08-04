from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from business_assistant.application.leads import (
    FieldValidation,
    GradeBand,
    HandoffTrigger,
    InvalidAnswerError,
    MatchOperator,
    QualificationField,
    QualificationFieldType,
    QualificationSchema,
    ScoreRule,
    Sensitivity,
    detect_handoff,
    next_missing_field,
    score_answers,
    validate_answer,
)
from business_assistant.application.scheduling.engine import business_due_at
from business_assistant.domain.scheduling import BusinessSchedule, IntervalType, ScheduleInterval
from business_assistant.domain.shared import QualificationSchemaId, ScheduleId, TenantId


def field(
    key: str,
    kind: QualificationFieldType,
    validation: FieldValidation | None = None,
    *,
    order: int = 0,
    scores: tuple[ScoreRule, ...] = (),
    triggers: tuple[HandoffTrigger, ...] = (),
) -> QualificationField:
    return QualificationField(
        key,
        key.replace("_", " ").title(),
        f"Enter {key}",
        kind,
        validation or FieldValidation(max_length=100),
        True,
        order,
        Sensitivity.PERSONAL,
        scores,
        triggers,
    )


def schema(*fields: QualificationField) -> QualificationSchema:
    return QualificationSchema(
        QualificationSchemaId.new(),
        TenantId.new(),
        "service_request",
        1,
        "Service request",
        "demo-v1",
        "Prepare and respond to this fictional service request.",
        fields,
        (GradeBand(0, "C"), GradeBand(30, "B"), GradeBand(60, "A")),
        timedelta(hours=24),
        120,
        True,
        True,
    )


@pytest.mark.parametrize(
    ("kind", "raw", "validation", "expected"),
    [
        (
            QualificationFieldType.SHORT_TEXT,
            "  Ford   Focus ",
            FieldValidation(max_length=30),
            "Ford Focus",
        ),
        (
            QualificationFieldType.LONG_TEXT,
            "Engine rattles",
            FieldValidation(max_length=200),
            "Engine rattles",
        ),
        (
            QualificationFieldType.SINGLE_CHOICE,
            "URGENT",
            FieldValidation(options=("Routine", "Urgent")),
            "Urgent",
        ),
        (
            QualificationFieldType.MULTI_CHOICE,
            "Brakes, Fire",
            FieldValidation(options=("Brakes", "Fire")),
            ("Brakes", "Fire"),
        ),
        (QualificationFieldType.PHONE, "+1 555 010 0123", FieldValidation(), "+1 555 010 0123"),
        (QualificationFieldType.EMAIL, "DEMO@EXAMPLE.COM", FieldValidation(), "demo@example.com"),
        (QualificationFieldType.INTEGER, "2020", FieldValidation(minimum=Decimal(1900)), 2020),
        (
            QualificationFieldType.DECIMAL,
            "2.5",
            FieldValidation(maximum=Decimal(10)),
            Decimal("2.5"),
        ),
        (QualificationFieldType.BOOLEAN, "yes", FieldValidation(), True),
        (QualificationFieldType.DATE, "2026-08-04", FieldValidation(), date(2026, 8, 4)),
    ],
)
def test_all_supported_field_types_validate_deterministically(
    kind: QualificationFieldType,
    raw: str,
    validation: FieldValidation,
    expected: object,
) -> None:
    assert validate_answer(field("value", kind, validation), raw) == expected


@pytest.mark.parametrize(
    ("kind", "raw", "validation", "message"),
    [
        (
            QualificationFieldType.SINGLE_CHOICE,
            "maybe",
            FieldValidation(options=("Yes", "No")),
            "Choose one of",
        ),
        (QualificationFieldType.EMAIL, "invalid", FieldValidation(), "valid email"),
        (QualificationFieldType.INTEGER, "2.5", FieldValidation(), "whole number"),
        (QualificationFieldType.BOOLEAN, "maybe", FieldValidation(), "yes or no"),
        (QualificationFieldType.DATE, "tomorrow", FieldValidation(), "YYYY-MM-DD"),
    ],
)
def test_invalid_answers_return_stable_corrections(
    kind: QualificationFieldType,
    raw: str,
    validation: FieldValidation,
    message: str,
) -> None:
    with pytest.raises(InvalidAnswerError, match=message):
        validate_answer(field("value", kind, validation), raw)


def test_missing_scoring_and_safety_handoff_are_deterministic() -> None:
    urgency = field(
        "urgency",
        QualificationFieldType.SINGLE_CHOICE,
        FieldValidation(options=("Routine", "Urgent")),
        scores=(ScoreRule("urgent-score", MatchOperator.EQUALS, "Urgent", 70),),
    )
    issue = field(
        "issue",
        QualificationFieldType.LONG_TEXT,
        FieldValidation(max_length=500),
        order=1,
        triggers=(
            HandoffTrigger(
                "fuel-leak",
                MatchOperator.CONTAINS,
                "fuel leak",
                "fuel_leak",
                "urgent",
            ),
        ),
    )
    configured = schema(urgency, issue)
    assert next_missing_field(configured, {}) == urgency
    answers = {"urgency": "Urgent", "issue": "There may be a fuel leak"}
    assert score_answers(configured, answers).score == 70
    assert score_answers(configured, answers).grade == "A"
    trigger = detect_handoff(configured, answers)
    assert trigger is not None
    assert (trigger.reason_code, trigger.priority) == ("fuel_leak", "urgent")


def test_handoff_due_time_counts_only_effective_business_hours() -> None:
    tenant_id = TenantId.new()
    schedule = BusinessSchedule(
        ScheduleId.new(),
        tenant_id,
        "Main",
        "UTC",
        (
            ScheduleInterval(0, time(9), time(17), IntervalType.OPEN),
            ScheduleInterval(1, time(9), time(17), IntervalType.OPEN),
        ),
    )
    monday = datetime(2026, 8, 3, 16, 30, tzinfo=UTC)
    assert business_due_at(schedule, monday, timedelta(hours=2)) == datetime(
        2026, 8, 4, 10, 30, tzinfo=UTC
    )
