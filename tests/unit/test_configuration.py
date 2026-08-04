from uuid import uuid4

import pytest

from business_assistant.config import ConfigurationError, load_settings


def valid_environment() -> dict[str, str]:
    return {
        "APP_ENV": "development",
        "PUBLIC_BASE_URL": "http://localhost:8000",
        "DEFAULT_TENANT_TIMEZONE": "Europe/Moscow",
        "DEFAULT_LOCALE": "en",
        "SUPPORTED_LOCALES": "en",
        "DATABASE_URL": "postgresql+asyncpg://app@localhost:5432/business_assistant",
        "INTERNAL_API_ENABLED": "true",
        "INTERNAL_API_KEY": "local-phase-three-key",  # pragma: allowlist secret
        "INTERNAL_API_TENANT_ID": str(uuid4()),
        "INTERNAL_API_ROLE": "viewer",
    }


def test_valid_development_configuration_groups_settings() -> None:
    settings = load_settings(valid_environment())
    assert settings.application.environment == "development"
    assert settings.database.pool_size == 10
    assert settings.api.port == 8000
    assert not settings.telegram.enabled
    assert not settings.redis.enabled
    assert not settings.openai.enabled


def telegram_environment(*, mode: str = "webhook") -> dict[str, str]:
    values = valid_environment()
    values.update(
        {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_DELIVERY_MODE": mode,
            "TELEGRAM_BOT_TOKEN": "42:local-telegram-token",  # pragma: allowlist secret
            "TELEGRAM_BOT_ID": "42",
            "TELEGRAM_TENANT_ID": str(uuid4()),
            "CALLBACK_SIGNING_KEY": "local-callback-key",  # pragma: allowlist secret
        }
    )
    if mode == "webhook":
        values.update(
            {
                "TELEGRAM_WEBHOOK_SECRET": "local_webhook_secret",  # pragma: allowlist secret
                "TELEGRAM_WEBHOOK_PATH_SECRET": "local_path_secret",  # pragma: allowlist secret
                "TELEGRAM_WEBHOOK_BASE_URL": "https://demo.example",
            }
        )
    return values


def test_valid_telegram_webhook_and_polling_configuration() -> None:
    webhook = load_settings(telegram_environment())
    assert webhook.telegram.bot_id == 42
    assert webhook.telegram.delivery_mode == "webhook"
    assert not webhook.telegram.polling_enabled
    assert webhook.telegram.update_max_bytes == 1_048_576

    polling = load_settings(telegram_environment(mode="polling"))
    assert polling.telegram.polling_enabled
    assert polling.telegram.webhook_secret is None


@pytest.mark.parametrize(
    "field",
    [
        "TELEGRAM_BOT_ID",
        "TELEGRAM_TENANT_ID",
        "CALLBACK_SIGNING_KEY",
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_WEBHOOK_PATH_SECRET",
        "TELEGRAM_WEBHOOK_BASE_URL",
    ],
)
def test_enabled_telegram_requires_complete_tenant_bound_context(field: str) -> None:
    values = telegram_environment()
    values.pop(field)
    with pytest.raises(ConfigurationError, match=field):
        load_settings(values)


def test_telegram_rejects_invalid_modes_secrets_and_limits() -> None:
    values = telegram_environment()
    values["TELEGRAM_DELIVERY_MODE"] = "both"
    with pytest.raises(ConfigurationError, match="TELEGRAM_DELIVERY_MODE"):
        load_settings(values)
    values = telegram_environment()
    values["TELEGRAM_WEBHOOK_SECRET"] = "contains spaces"  # pragma: allowlist secret
    with pytest.raises(ConfigurationError, match="TELEGRAM_WEBHOOK_SECRET"):
        load_settings(values)
    values = telegram_environment()
    values["TELEGRAM_CALLBACK_EXPIRY_SECONDS"] = "1"
    with pytest.raises(ConfigurationError, match="TELEGRAM_CALLBACK_EXPIRY_SECONDS"):
        load_settings(values)


def test_disabled_integrations_do_not_require_credentials() -> None:
    values = valid_environment()
    values["INTERNAL_API_ENABLED"] = "false"
    values.pop("INTERNAL_API_KEY")
    values.pop("INTERNAL_API_TENANT_ID")
    settings = load_settings(values)
    assert settings.security.internal_api_key is None
    assert settings.telegram.bot_token is None


@pytest.mark.parametrize(
    ("enabled", "required_field"),
    [
        ("TELEGRAM_ENABLED", "TELEGRAM_BOT_TOKEN"),
        ("REDIS_ENABLED", "REDIS_URL"),
        ("CELERY_ENABLED", "CELERY_BROKER_URL"),
        ("OPENAI_ENABLED", "OPENAI_API_KEY"),
    ],
)
def test_enabled_integrations_require_only_their_credentials(
    enabled: str, required_field: str
) -> None:
    values = valid_environment()
    values[enabled] = "true"
    with pytest.raises(ConfigurationError, match=required_field):
        load_settings(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("APP_ENV", "preview"),
        ("DATABASE_URL", "sqlite:///demo.db"),
        ("PUBLIC_BASE_URL", "not-a-url"),
        ("DEFAULT_TENANT_TIMEZONE", "Mars/Olympus"),
        ("SUPPORTED_LOCALES", "en,fr"),
        ("DATABASE_POOL_SIZE", "0"),
        ("API_PORT", "70000"),
        ("API_REQUEST_TIMEOUT_SECONDS", "0"),
        ("DEFAULT_TENANT_SLUG", "Not URL Safe"),
        ("LOG_FORMAT", "xml"),
        ("UPLOAD_MAX_BYTES", "100"),
        ("EMBEDDING_DIMENSIONS", "0"),
    ],
)
def test_invalid_configuration_is_rejected(field: str, value: str) -> None:
    values = valid_environment()
    values[field] = value
    with pytest.raises(ConfigurationError, match=field):
        load_settings(values)


def test_production_rejects_http_polling_and_unsafe_secret_without_leaking_it() -> None:
    values = valid_environment()
    values.update(
        {
            "APP_ENV": "production",
            "PUBLIC_BASE_URL": "https://business.example",
            "INTERNAL_API_KEY": "unsafe-phase3-value",  # pragma: allowlist secret
        }
    )
    with pytest.raises(ConfigurationError) as captured:
        load_settings(values)
    assert "unsafe-phase3-value" not in str(captured.value)


def test_production_rejects_long_placeholder_secret() -> None:
    values = valid_environment()
    unsafe_placeholder = "placeholder-xxxxxxxxxxxxxxxxxxxxxxxx"  # pragma: allowlist secret
    values.update(
        {
            "APP_ENV": "production",
            "PUBLIC_BASE_URL": "https://business.example",
            "INTERNAL_API_KEY": unsafe_placeholder,
        }
    )
    with pytest.raises(ConfigurationError, match="INTERNAL_API_KEY"):
        load_settings(values)

    values["INTERNAL_API_KEY"] = "x" * 40
    values["TELEGRAM_POLLING_ENABLED"] = "true"
    with pytest.raises(ConfigurationError, match="TELEGRAM_POLLING_ENABLED"):
        load_settings(values)


def test_ai_feature_requires_enabled_provider() -> None:
    values = valid_environment()
    values["AI_ENABLED"] = "true"
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        load_settings(values)


def test_enabled_openai_and_rag_require_explicit_model_policy() -> None:
    values = valid_environment()
    values.update(
        {
            "OPENAI_ENABLED": "true",
            "OPENAI_API_KEY": "local-openai-fixture",  # pragma: allowlist secret
            "OPENAI_ROUTER_MODEL": "router-fixture",
            "OPENAI_RESPONSE_MODEL": "response-fixture",
        }
    )
    settings = load_settings(values)
    assert settings.openai.router_model == "router-fixture"

    values.update({"FEATURE_AI_ENABLED": "true", "FEATURE_RAG_ENABLED": "true"})
    with pytest.raises(ConfigurationError, match="OPENAI_EMBEDDING_MODEL"):
        load_settings(values)
    values.update({"OPENAI_EMBEDDING_MODEL": "embedding-fixture", "EMBEDDING_DIMENSIONS": "1536"})
    assert load_settings(values).openai.embedding_dimensions == 1536


def test_provider_neutral_ai_policy_is_externalized_and_legacy_aliases_remain_compatible() -> None:
    values = valid_environment()
    values.update(
        {
            "AI_ENABLED": "true",
            "AI_PROVIDER": "openai",
            "AI_ROUTER_MODEL": "router-fixture",
            "AI_RESPONSE_MODEL": "response-fixture",
            "AI_TIMEOUT_SECONDS": "7.5",
            "AI_MAX_RETRIES": "3",
            "AI_CONFIDENCE_THRESHOLD": "0.85",
            "AI_INPUT_COST_PER_MILLION": "1.25",
            "AI_OUTPUT_COST_PER_MILLION": "5",
            "OPENAI_API_KEY": "local-openai-fixture",  # pragma: allowlist secret
        }
    )
    settings = load_settings(values)
    assert settings.ai.enabled and settings.ai.provider == "openai"
    assert settings.ai.timeout_seconds == 7.5
    assert settings.ai.confidence_threshold == 0.85
    assert settings.openai.router_model == "router-fixture"

    values["FEATURE_AI_ENABLED"] = "false"
    with pytest.raises(ConfigurationError, match="conflicts"):
        load_settings(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AI_PROVIDER", "unknown"),
        ("AI_TIMEOUT_SECONDS", "0"),
        ("AI_MAX_RETRIES", "6"),
        ("AI_CONFIDENCE_THRESHOLD", "1.1"),
        ("AI_STRUCTURED_OUTPUT_MODE", "json_object"),
        ("AI_INPUT_COST_PER_MILLION", "-1"),
    ],
)
def test_enabled_ai_rejects_invalid_provider_and_policy(field: str, value: str) -> None:
    values = valid_environment()
    values.update(
        {
            "AI_ENABLED": "true",
            "AI_ROUTER_MODEL": "router-fixture",
            "AI_RESPONSE_MODEL": "response-fixture",
            "OPENAI_API_KEY": "local-openai-fixture",  # pragma: allowlist secret
            field: value,
        }
    )
    with pytest.raises(ConfigurationError, match=field):
        load_settings(values)


def test_celery_result_backend_is_conditional() -> None:
    values = valid_environment()
    values.update(
        {
            "CELERY_ENABLED": "true",
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULTS_ENABLED": "true",
        }
    )
    with pytest.raises(ConfigurationError, match="CELERY_RESULT_BACKEND"):
        load_settings(values)


def test_production_rejects_sensitive_logging_and_admin_bootstrap() -> None:
    values = valid_environment()
    values.update(
        {
            "APP_ENV": "production",
            "PUBLIC_BASE_URL": "https://business.example",
            "INTERNAL_API_KEY": "x" * 40,
            "LOG_INCLUDE_MESSAGE_TEXT": "true",
        }
    )
    with pytest.raises(ConfigurationError, match="LOG_INCLUDE_MESSAGE_TEXT"):
        load_settings(values)
    values["LOG_INCLUDE_MESSAGE_TEXT"] = "false"
    values["ADMIN_BOOTSTRAP_TOKEN"] = "x" * 40
    with pytest.raises(ConfigurationError, match="ADMIN_BOOTSTRAP_TOKEN"):
        load_settings(values)
