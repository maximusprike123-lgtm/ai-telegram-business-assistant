"""Strict JSON schemas and standard-library validation for AI task outputs."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from .models import (
    AIRequest,
    AIResult,
    AITask,
    ClassificationResult,
    ExtractedField,
    ExtractionResult,
    Intent,
    IntentResult,
    RewriteResult,
    RiskFlag,
    SuggestedAction,
    SummaryResult,
)


class AISchemaValidationError(ValueError):
    pass


def _object(value: object, required: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != set(required):
        raise AISchemaValidationError("AI output object shape is invalid")
    if not all(isinstance(key, str) for key in value):
        raise AISchemaValidationError("AI output keys must be strings")
    return cast(Mapping[str, object], value)


def _string(value: object, *, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AISchemaValidationError("AI output string is invalid")
    return value


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AISchemaValidationError("AI output confidence must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise AISchemaValidationError("AI output confidence is out of range")
    return result


def _strings(
    value: object, *, maximum_items: int = 20, maximum_length: int = 500
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AISchemaValidationError("AI output list is invalid")
    if len(value) > maximum_items:
        raise AISchemaValidationError("AI output list is too long")
    return tuple(_string(item, maximum=maximum_length) for item in value)


def _field(value: object) -> ExtractedField:
    item = _object(value, frozenset({"key", "value", "confidence"}))
    try:
        return ExtractedField(
            _string(item["key"], maximum=100),
            _string(item["value"], maximum=1000),
            _confidence(item["confidence"]),
        )
    except ValueError as exc:
        raise AISchemaValidationError("AI extracted field is invalid") from exc


def _fields(value: object) -> tuple[ExtractedField, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) > 30:
        raise AISchemaValidationError("AI extracted fields are invalid")
    return tuple(_field(item) for item in value)


def parse_result(request: AIRequest, output: Mapping[str, Any]) -> AIResult:
    try:
        if request.task is AITask.INTENT:
            item = _object(
                output,
                frozenset(
                    {
                        "intent",
                        "confidence",
                        "entities",
                        "missing_information",
                        "risk_flags",
                        "suggested_action",
                        "rationale_category",
                    }
                ),
            )
            result: AIResult = IntentResult(
                Intent(_string(item["intent"], maximum=100)),
                _confidence(item["confidence"]),
                _fields(item["entities"]),
                _strings(item["missing_information"], maximum_items=10, maximum_length=100),
                tuple(RiskFlag(value) for value in _strings(item["risk_flags"], maximum_items=4)),
                SuggestedAction(_string(item["suggested_action"], maximum=100)),
                _string(item["rationale_category"], maximum=100),
            )
        elif request.task is AITask.EXTRACTION:
            item = _object(output, frozenset({"fields", "confidence"}))
            result = ExtractionResult(_fields(item["fields"]), _confidence(item["confidence"]))
        elif request.task is AITask.CLASSIFICATION:
            item = _object(output, frozenset({"label", "confidence", "rationale_category"}))
            result = ClassificationResult(
                _string(item["label"], maximum=100),
                _confidence(item["confidence"]),
                _string(item["rationale_category"], maximum=100),
            )
        elif request.task is AITask.REWRITE:
            item = _object(output, frozenset({"text", "confidence"}))
            result = RewriteResult(_string(item["text"]), _confidence(item["confidence"]))
        else:
            item = _object(output, frozenset({"summary", "key_points", "confidence"}))
            result = SummaryResult(
                _string(item["summary"]),
                _strings(item["key_points"], maximum_items=10),
                _confidence(item["confidence"]),
            )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, AISchemaValidationError):
            raise
        raise AISchemaValidationError("AI output contains an unsupported value") from exc
    validate_application_result(request, result)
    return result


def validate_application_result(request: AIRequest, result: AIResult) -> None:
    if isinstance(result, IntentResult):
        entity_keys = {item.key for item in result.entities}
        if len(entity_keys) != len(result.entities):
            raise AISchemaValidationError("AI intent entities must be unique")
        high_risk = result.intent in {Intent.HIGH_RISK, Intent.COMPLAINT} or bool(
            set(result.risk_flags) & {RiskFlag.HIGH_RISK, RiskFlag.SAFETY, RiskFlag.COMPLAINT}
        )
        if high_risk and result.suggested_action is not SuggestedAction.OFFER_HUMAN:
            raise AISchemaValidationError("High-risk intent must offer human help")
    elif isinstance(result, ExtractionResult):
        if any(item.key not in request.allowed_extraction_fields for item in result.fields):
            raise AISchemaValidationError("AI extraction returned a field outside the allowlist")
    elif isinstance(result, ClassificationResult):
        if result.label not in request.allowed_classification_labels:
            raise AISchemaValidationError(
                "AI classification returned a label outside the allowlist"
            )


def confidence_of(result: AIResult) -> float:
    return result.confidence


def fallback_result(request: AIRequest) -> AIResult:
    if request.task is AITask.INTENT:
        return IntentResult(
            Intent.UNKNOWN,
            0,
            (),
            (),
            (),
            SuggestedAction.OFFER_HUMAN,
            "deterministic_fallback",
        )
    if request.task is AITask.EXTRACTION:
        return ExtractionResult((), 0)
    if request.task is AITask.CLASSIFICATION:
        return ClassificationResult("unknown", 0, "deterministic_fallback")
    if request.task is AITask.REWRITE:
        return RewriteResult(request.input_text, 0)
    return SummaryResult("A verified summary is unavailable.", (), 0)


def json_schema_for(request: AIRequest) -> dict[str, Any]:
    confidence = {"type": "number", "minimum": 0, "maximum": 1}
    extracted_field: dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "minLength": 1, "maxLength": 100},
            "value": {"type": "string", "minLength": 1, "maxLength": 1000},
            "confidence": confidence,
        },
        "required": ["key", "value", "confidence"],
        "additionalProperties": False,
    }
    if request.task is AITask.INTENT:
        return _schema(
            {
                "intent": {"type": "string", "enum": [item.value for item in Intent]},
                "confidence": confidence,
                "entities": {"type": "array", "items": extracted_field, "maxItems": 30},
                "missing_information": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 100},
                    "maxItems": 10,
                },
                "risk_flags": {
                    "type": "array",
                    "items": {"type": "string", "enum": [item.value for item in RiskFlag]},
                    "maxItems": 4,
                },
                "suggested_action": {
                    "type": "string",
                    "enum": [item.value for item in SuggestedAction],
                },
                "rationale_category": {"type": "string", "minLength": 1, "maxLength": 100},
            }
        )
    if request.task is AITask.EXTRACTION:
        extracted_field["properties"]["key"] = {
            "type": "string",
            "enum": sorted(request.allowed_extraction_fields),
        }
        return _schema(
            {
                "fields": {"type": "array", "items": extracted_field, "maxItems": 30},
                "confidence": confidence,
            }
        )
    if request.task is AITask.CLASSIFICATION:
        return _schema(
            {
                "label": {
                    "type": "string",
                    "enum": sorted(request.allowed_classification_labels),
                },
                "confidence": confidence,
                "rationale_category": {"type": "string", "minLength": 1, "maxLength": 100},
            }
        )
    if request.task is AITask.REWRITE:
        return _schema(
            {
                "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                "confidence": confidence,
            }
        )
    return _schema(
        {
            "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
            "key_points": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 500},
                "maxItems": 10,
            },
            "confidence": confidence,
        }
    )


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
