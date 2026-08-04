"""Immutable, composition-boundary runtime configuration and safe validation."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from business_assistant.application.common.security import Role
from business_assistant.domain.shared import Locale, TenantId


class ConfigurationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        super().__init__(f"Invalid configuration for {field}: {reason}")


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    return values.get(name, default).strip()


def _boolean(values: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = _text(values, name, "true" if default else "false").lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ConfigurationError(name, "must be a boolean")
    return value in {"true", "1", "yes"}


def _integer(values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(_text(values, name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(name, "must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(name, f"must be between {minimum} and {maximum}")
    return value


def _number(
    values: Mapping[str, str], name: str, default: float, minimum: float, maximum: float
) -> float:
    try:
        value = float(_text(values, name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(name, "must be a number") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(name, f"must be between {minimum} and {maximum}")
    return value


def _decimal(
    values: Mapping[str, str], name: str, default: str, minimum: Decimal, maximum: Decimal
) -> Decimal:
    try:
        value = Decimal(_text(values, name, default))
    except InvalidOperation as exc:
        raise ConfigurationError(name, "must be a decimal number") from exc
    if not value.is_finite() or not minimum <= value <= maximum:
        raise ConfigurationError(name, f"must be between {minimum} and {maximum}")
    return value


def _url(
    values: Mapping[str, str], name: str, *, schemes: frozenset[str], required: bool
) -> str | None:
    value = _text(values, name)
    if not value:
        if required:
            raise ConfigurationError(name, "is required")
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise ConfigurationError(name, "has an unsupported URL scheme or missing host")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ConfigurationError(name, "contains an invalid port")
    return value


def _secret(
    values: Mapping[str, str], name: str, *, required: bool, production: bool
) -> str | None:
    value = _text(values, name)
    if not value:
        if required:
            raise ConfigurationError(name, "is required when the feature is enabled")
        return None
    normalized = value.lower()
    unsafe_markers = ("change-me", "changeme", "replace-me", "placeholder", "example")
    if production and (
        len(value) < 32
        or normalized in {"secret", "test"}
        or any(x in normalized for x in unsafe_markers)
    ):
        raise ConfigurationError(name, "must be a strong non-placeholder production secret")
    return value


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    environment: str
    public_base_url: str
    default_tenant_slug: str
    default_timezone: str
    default_locale: Locale
    supported_locales: frozenset[Locale]


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    url: str
    pool_size: int
    max_overflow: int
    connect_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ApiConfig:
    enabled: bool
    host: str
    port: int
    request_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    internal_api_key: str | None
    internal_api_tenant_id: TenantId | None
    internal_api_role: Role | None
    callback_signing_key: str | None
    confirmation_signing_key: str | None
    field_encryption_key: str | None
    admin_bootstrap_token: str | None


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    enabled: bool
    delivery_mode: str
    bot_token: str | None
    bot_id: int | None
    tenant_id: TenantId | None
    webhook_secret: str | None
    webhook_path_secret: str | None
    webhook_base_url: str | None
    update_max_bytes: int
    callback_version: int
    callback_expiry_seconds: int
    deduplication_retention_days: int
    processing_stale_seconds: int

    @property
    def polling_enabled(self) -> bool:
        return self.enabled and self.delivery_mode == "polling"


@dataclass(frozen=True, slots=True)
class RedisConfig:
    enabled: bool
    url: str | None


@dataclass(frozen=True, slots=True)
class CeleryConfig:
    enabled: bool
    broker_url: str | None
    results_enabled: bool
    result_backend_url: str | None


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    enabled: bool
    api_key: str | None
    router_model: str | None
    response_model: str | None
    embedding_model: str | None
    embedding_dimensions: int | None
    max_tool_iterations: int
    max_output_tokens: int
    base_url: str


@dataclass(frozen=True, slots=True)
class AIRuntimeConfig:
    enabled: bool
    provider: str
    router_model: str | None
    response_model: str | None
    temperature: float | None
    timeout_seconds: float
    max_retries: int
    confidence_threshold: float
    structured_output_mode: str
    max_output_tokens: int
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal


@dataclass(frozen=True, slots=True)
class KnowledgeConfig:
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    candidate_limit: int
    result_limit: int
    minimum_relevance: float
    maximum_answer_characters: int


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    log_level: str
    log_format: str
    include_message_text: bool
    otlp_endpoint: str | None
    metrics_auth_token: str | None


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    ai_enabled: bool
    rag_enabled: bool
    automatic_handoff_enabled: bool


@dataclass(frozen=True, slots=True)
class LimitConfig:
    upload_max_bytes: int
    message_retention_days: int
    ai_telemetry_retention_days: int
    messages_per_minute: int
    ai_calls_per_minute: int


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    application: ApplicationConfig
    database: DatabaseConfig
    api: ApiConfig
    security: SecurityConfig
    telegram: TelegramConfig
    redis: RedisConfig
    celery: CeleryConfig
    openai: OpenAIConfig
    ai: AIRuntimeConfig
    knowledge: KnowledgeConfig
    observability: ObservabilityConfig
    features: FeatureConfig
    limits: LimitConfig


def load_settings(environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = dict(os.environ if environ is None else environ)
    environment = _text(values, "APP_ENV", "local").lower()
    if environment not in {"local", "development", "test", "staging", "production"}:
        raise ConfigurationError(
            "APP_ENV", "must be local, development, test, staging, or production"
        )
    production = environment == "production"
    public_base_url = _url(
        values, "PUBLIC_BASE_URL", schemes=frozenset({"http", "https"}), required=True
    )
    assert public_base_url is not None
    if production and not public_base_url.startswith("https://"):
        raise ConfigurationError("PUBLIC_BASE_URL", "must use HTTPS in production")
    default_tenant_slug = _text(values, "DEFAULT_TENANT_SLUG", "northstar-auto-care")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", default_tenant_slug) is None:
        raise ConfigurationError("DEFAULT_TENANT_SLUG", "must be a lowercase URL-safe slug")
    timezone = _text(values, "DEFAULT_TENANT_TIMEZONE", "UTC")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError("DEFAULT_TENANT_TIMEZONE", "must be an IANA timezone") from exc
    try:
        default_locale = Locale(_text(values, "DEFAULT_LOCALE", "en"))
        supported = frozenset(
            Locale(item.strip())
            for item in _text(values, "SUPPORTED_LOCALES", "en").split(",")
            if item.strip()
        )
    except ValueError as exc:
        raise ConfigurationError("SUPPORTED_LOCALES", "contains an unsupported locale") from exc
    if not supported or default_locale not in supported:
        raise ConfigurationError("DEFAULT_LOCALE", "must be included in SUPPORTED_LOCALES")
    database_url = _url(
        values, "DATABASE_URL", schemes=frozenset({"postgresql+asyncpg"}), required=True
    )
    assert database_url is not None
    api_enabled = _boolean(values, "INTERNAL_API_ENABLED", True)
    api_key = _secret(values, "INTERNAL_API_KEY", required=api_enabled, production=production)
    tenant_id: TenantId | None = None
    role: Role | None = None
    if api_enabled:
        try:
            tenant_id = TenantId(UUID(_text(values, "INTERNAL_API_TENANT_ID")))
        except (ValueError, AttributeError) as exc:
            raise ConfigurationError("INTERNAL_API_TENANT_ID", "must be a UUID") from exc
        try:
            role = Role(_text(values, "INTERNAL_API_ROLE", "viewer"))
        except ValueError as exc:
            raise ConfigurationError("INTERNAL_API_ROLE", "contains an unsupported role") from exc
    telegram_enabled = _boolean(values, "TELEGRAM_ENABLED", False)
    telegram_bot_token = _secret(
        values, "TELEGRAM_BOT_TOKEN", required=telegram_enabled, production=production
    )
    telegram_mode = _text(values, "TELEGRAM_DELIVERY_MODE", "webhook").lower()
    legacy_polling = _boolean(values, "TELEGRAM_POLLING_ENABLED", False)
    if legacy_polling:
        if "TELEGRAM_DELIVERY_MODE" in values and telegram_mode != "polling":
            raise ConfigurationError(
                "TELEGRAM_POLLING_ENABLED", "conflicts with TELEGRAM_DELIVERY_MODE"
            )
        telegram_mode = "polling"
    if telegram_mode not in {"webhook", "polling"}:
        raise ConfigurationError("TELEGRAM_DELIVERY_MODE", "must be webhook or polling")
    if production and legacy_polling:
        raise ConfigurationError("TELEGRAM_POLLING_ENABLED", "cannot be enabled in production")
    if production and telegram_enabled and telegram_mode != "webhook":
        raise ConfigurationError("TELEGRAM_DELIVERY_MODE", "must be webhook in production")
    telegram_bot_id: int | None = None
    telegram_tenant_id: TenantId | None = None
    if telegram_enabled:
        telegram_bot_id = _integer(values, "TELEGRAM_BOT_ID", 0, 1, 9_999_999_999_999)
        try:
            telegram_tenant_id = TenantId(UUID(_text(values, "TELEGRAM_TENANT_ID")))
        except (ValueError, AttributeError) as exc:
            raise ConfigurationError("TELEGRAM_TENANT_ID", "must be a UUID") from exc
    webhook_base_url = _url(
        values,
        "TELEGRAM_WEBHOOK_BASE_URL",
        schemes=frozenset({"http", "https"}),
        required=telegram_enabled and telegram_mode == "webhook",
    )
    if production and webhook_base_url is not None and not webhook_base_url.startswith("https://"):
        raise ConfigurationError("TELEGRAM_WEBHOOK_BASE_URL", "must use HTTPS in production")
    callback_signing_key = _secret(
        values, "CALLBACK_SIGNING_KEY", required=telegram_enabled, production=production
    )
    webhook_secret_value = _secret(
        values,
        "TELEGRAM_WEBHOOK_SECRET",
        required=telegram_enabled and telegram_mode == "webhook",
        production=production,
    )
    if (
        webhook_secret_value is not None
        and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", webhook_secret_value) is None
    ):
        raise ConfigurationError(
            "TELEGRAM_WEBHOOK_SECRET",
            "must use 1-256 ASCII letters, digits, underscores, or hyphens",
        )
    webhook_path_secret_value = _secret(
        values,
        "TELEGRAM_WEBHOOK_PATH_SECRET",
        required=telegram_enabled and telegram_mode == "webhook",
        production=production,
    )
    if (
        webhook_path_secret_value is not None
        and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", webhook_path_secret_value) is None
    ):
        raise ConfigurationError(
            "TELEGRAM_WEBHOOK_PATH_SECRET",
            "must use 1-256 ASCII letters, digits, underscores, or hyphens",
        )
    redis_enabled = _boolean(values, "REDIS_ENABLED", False)
    celery_enabled = _boolean(values, "CELERY_ENABLED", False)
    celery_results_enabled = _boolean(values, "CELERY_RESULTS_ENABLED", False)
    openai_enabled = _boolean(values, "OPENAI_ENABLED", False)
    legacy_ai_enabled = _boolean(values, "FEATURE_AI_ENABLED", False)
    ai_enabled = _boolean(values, "AI_ENABLED", legacy_ai_enabled)
    if (
        "AI_ENABLED" in values
        and "FEATURE_AI_ENABLED" in values
        and ai_enabled != legacy_ai_enabled
    ):
        raise ConfigurationError("AI_ENABLED", "conflicts with FEATURE_AI_ENABLED")
    ai_provider = _text(values, "AI_PROVIDER", "openai").lower()
    if ai_enabled and ai_provider not in {"openai"}:
        raise ConfigurationError("AI_PROVIDER", "has no configured provider adapter")
    openai_enabled = openai_enabled or (ai_enabled and ai_provider == "openai")
    features = FeatureConfig(
        ai_enabled=ai_enabled,
        rag_enabled=_boolean(values, "FEATURE_RAG_ENABLED", False),
        automatic_handoff_enabled=_boolean(values, "FEATURE_AUTOMATIC_HANDOFF_ENABLED", False),
    )
    if features.ai_enabled and not openai_enabled:
        raise ConfigurationError("AI_ENABLED", "requires an enabled provider")
    if features.rag_enabled and (not features.ai_enabled or not openai_enabled):
        raise ConfigurationError("FEATURE_RAG_ENABLED", "requires AI and OpenAI to be enabled")
    log_level = _text(values, "LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("LOG_LEVEL", "contains an unsupported level")
    log_format = _text(values, "LOG_FORMAT", "json").lower()
    if log_format not in {"json", "text"}:
        raise ConfigurationError("LOG_FORMAT", "must be json or text")
    include_message_text = _boolean(values, "LOG_INCLUDE_MESSAGE_TEXT", False)
    if production and include_message_text:
        raise ConfigurationError("LOG_INCLUDE_MESSAGE_TEXT", "cannot be enabled in production")
    embedding_dimensions_text = _text(values, "EMBEDDING_DIMENSIONS")
    embedding_dimensions = (
        _integer(values, "EMBEDDING_DIMENSIONS", 1536, 1, 65535)
        if embedding_dimensions_text
        else None
    )
    router_model = _text(values, "AI_ROUTER_MODEL", _text(values, "OPENAI_ROUTER_MODEL")) or None
    response_model = (
        _text(values, "AI_RESPONSE_MODEL", _text(values, "OPENAI_RESPONSE_MODEL")) or None
    )
    embedding_model = _text(values, "OPENAI_EMBEDDING_MODEL") or None
    openai_api_key = _secret(
        values, "OPENAI_API_KEY", required=openai_enabled, production=production
    )
    if openai_enabled and (router_model is None or response_model is None):
        raise ConfigurationError("AI_ROUTER_MODEL", "router and response models are required")
    if features.rag_enabled and (embedding_model is None or embedding_dimensions is None):
        raise ConfigurationError(
            "OPENAI_EMBEDDING_MODEL", "embedding model and dimensions are required for RAG"
        )
    chunk_max_tokens = _integer(values, "KNOWLEDGE_CHUNK_MAX_TOKENS", 500, 50, 1000)
    chunk_overlap_tokens = _integer(values, "KNOWLEDGE_CHUNK_OVERLAP_TOKENS", 50, 0, 499)
    if chunk_overlap_tokens >= chunk_max_tokens // 2:
        raise ConfigurationError(
            "KNOWLEDGE_CHUNK_OVERLAP_TOKENS", "must be less than half the chunk maximum"
        )
    retrieval_candidate_limit = _integer(values, "RAG_CANDIDATE_LIMIT", 20, 1, 100)
    retrieval_result_limit = _integer(values, "RAG_RESULT_LIMIT", 4, 1, 20)
    if retrieval_result_limit > retrieval_candidate_limit:
        raise ConfigurationError("RAG_RESULT_LIMIT", "cannot exceed RAG_CANDIDATE_LIMIT")
    structured_output_mode = _text(values, "AI_STRUCTURED_OUTPUT_MODE", "strict_json_schema")
    if structured_output_mode != "strict_json_schema":
        raise ConfigurationError("AI_STRUCTURED_OUTPUT_MODE", "must be strict_json_schema")
    openai_base_url = (
        _url(
            values,
            "OPENAI_BASE_URL",
            schemes=frozenset({"http", "https"}),
            required=False,
        )
        or "https://api.openai.com/v1"
    )
    if production and openai_enabled and not openai_base_url.startswith("https://"):
        raise ConfigurationError("OPENAI_BASE_URL", "must use HTTPS in production")
    admin_token = _secret(values, "ADMIN_BOOTSTRAP_TOKEN", required=False, production=production)
    if production and admin_token is not None:
        raise ConfigurationError("ADMIN_BOOTSTRAP_TOKEN", "is local-development only")
    return RuntimeSettings(
        application=ApplicationConfig(
            environment,
            public_base_url,
            default_tenant_slug,
            timezone,
            default_locale,
            supported,
        ),
        database=DatabaseConfig(
            database_url,
            _integer(values, "DATABASE_POOL_SIZE", 10, 1, 100),
            _integer(values, "DATABASE_MAX_OVERFLOW", 10, 0, 100),
            _integer(values, "DATABASE_CONNECT_TIMEOUT_SECONDS", 10, 1, 120),
        ),
        api=ApiConfig(
            api_enabled,
            _text(values, "API_HOST", "127.0.0.1"),
            _integer(values, "API_PORT", 8000, 1, 65535),
            _integer(values, "API_REQUEST_TIMEOUT_SECONDS", 15, 1, 120),
        ),
        security=SecurityConfig(
            api_key,
            tenant_id,
            role,
            callback_signing_key,
            _secret(values, "CONFIRMATION_SIGNING_KEY", required=False, production=production),
            _secret(values, "FIELD_ENCRYPTION_KEY", required=False, production=production),
            admin_token,
        ),
        telegram=TelegramConfig(
            telegram_enabled,
            telegram_mode,
            telegram_bot_token,
            telegram_bot_id,
            telegram_tenant_id,
            webhook_secret_value,
            webhook_path_secret_value,
            webhook_base_url,
            _integer(values, "TELEGRAM_UPDATE_MAX_BYTES", 1_048_576, 1024, 10_485_760),
            _integer(values, "TELEGRAM_CALLBACK_VERSION", 1, 1, 99),
            _integer(values, "TELEGRAM_CALLBACK_EXPIRY_SECONDS", 900, 30, 86_400),
            _integer(values, "TELEGRAM_DEDUPLICATION_RETENTION_DAYS", 7, 1, 90),
            _integer(values, "TELEGRAM_PROCESSING_STALE_SECONDS", 60, 5, 3600),
        ),
        redis=RedisConfig(
            redis_enabled,
            _url(
                values, "REDIS_URL", schemes=frozenset({"redis", "rediss"}), required=redis_enabled
            ),
        ),
        celery=CeleryConfig(
            celery_enabled,
            _url(
                values,
                "CELERY_BROKER_URL",
                schemes=frozenset({"redis", "rediss", "amqp", "amqps"}),
                required=celery_enabled,
            ),
            celery_results_enabled,
            _url(
                values,
                "CELERY_RESULT_BACKEND",
                schemes=frozenset({"redis", "rediss", "db+postgresql"}),
                required=celery_enabled and celery_results_enabled,
            ),
        ),
        openai=OpenAIConfig(
            openai_enabled,
            openai_api_key,
            router_model,
            response_model,
            embedding_model,
            embedding_dimensions,
            _integer(values, "AI_MAX_TOOL_ITERATIONS", 4, 1, 16),
            _integer(values, "AI_MAX_OUTPUT_TOKENS", 800, 64, 32768),
            openai_base_url,
        ),
        ai=AIRuntimeConfig(
            ai_enabled,
            ai_provider,
            router_model,
            response_model,
            (
                _number(values, "AI_TEMPERATURE", 0, 0, 2)
                if _text(values, "AI_TEMPERATURE", "0").lower() != "none"
                else None
            ),
            _number(values, "AI_TIMEOUT_SECONDS", 8, 0.1, 120),
            _integer(values, "AI_MAX_RETRIES", 2, 0, 5),
            _number(values, "AI_CONFIDENCE_THRESHOLD", 0.8, 0, 1),
            structured_output_mode,
            _integer(values, "AI_MAX_OUTPUT_TOKENS", 800, 64, 32768),
            _decimal(values, "AI_INPUT_COST_PER_MILLION", "0", Decimal(0), Decimal(1_000_000)),
            _decimal(values, "AI_OUTPUT_COST_PER_MILLION", "0", Decimal(0), Decimal(1_000_000)),
        ),
        knowledge=KnowledgeConfig(
            chunk_max_tokens,
            chunk_overlap_tokens,
            retrieval_candidate_limit,
            retrieval_result_limit,
            _number(values, "RAG_MIN_RELEVANCE", 0.6, 0.5, 1),
            _integer(values, "RAG_MAX_ANSWER_CHARACTERS", 1800, 200, 4000),
        ),
        observability=ObservabilityConfig(
            log_level,
            log_format,
            include_message_text,
            _url(
                values,
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                schemes=frozenset({"http", "https", "grpc"}),
                required=False,
            ),
            _secret(values, "METRICS_AUTH_TOKEN", required=False, production=production),
        ),
        features=features,
        limits=LimitConfig(
            _integer(values, "UPLOAD_MAX_BYTES", 10_485_760, 1024, 1_073_741_824),
            _integer(values, "MESSAGE_RETENTION_DAYS", 90, 1, 3650),
            _integer(values, "AI_TELEMETRY_RETENTION_DAYS", 90, 1, 3650),
            _integer(values, "RATE_LIMIT_MESSAGES_PER_MINUTE", 30, 1, 10000),
            _integer(values, "RATE_LIMIT_AI_CALLS_PER_MINUTE", 10, 1, 10000),
        ),
    )
