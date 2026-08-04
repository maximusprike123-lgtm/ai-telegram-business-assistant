"""Phase 7 AI composition without import-time network activity."""

from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.ai import (
    AdvisoryRoutingValidator,
    AIRuntime,
    AITask,
    AITextRouter,
    ModelPolicy,
)
from business_assistant.config import RuntimeSettings
from business_assistant.infrastructure.ai import (
    AIProviderRegistry,
    OpenAIResponsesAdapter,
    StaticModelPolicyCatalog,
    VersionedPromptCatalog,
    default_prompts,
)
from business_assistant.infrastructure.persistence import SQLAlchemyAITelemetryStore


def build_ai_router(
    settings: RuntimeSettings,
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient | None,
) -> AITextRouter:
    providers = []
    if settings.ai.enabled:
        if client is None or settings.openai.api_key is None:
            raise ValueError("Enabled AI runtime requires a configured provider client")
        providers.append(
            OpenAIResponsesAdapter(
                client,
                settings.openai.api_key,
                base_url=settings.openai.base_url,
            )
        )
    policies = _policies(settings) if settings.ai.enabled else ()
    runtime = AIRuntime(
        enabled=settings.ai.enabled,
        providers=AIProviderRegistry(providers),
        prompts=VersionedPromptCatalog(default_prompts()),
        policies=StaticModelPolicyCatalog(policies),
        telemetry=SQLAlchemyAITelemetryStore(session_factory),
        business_validator=AdvisoryRoutingValidator(),
    )
    return AITextRouter(runtime)


def _policies(settings: RuntimeSettings) -> tuple[ModelPolicy, ...]:
    router_model, response_model = settings.ai.router_model, settings.ai.response_model
    if router_model is None or response_model is None:
        raise ValueError("Enabled AI runtime requires task models")
    prompt_schema = {
        AITask.INTENT: ("intent-router", "intent-v1", router_model),
        AITask.EXTRACTION: ("field-extractor", "extraction-v1", router_model),
        AITask.CLASSIFICATION: ("classifier", "classification-v1", router_model),
        AITask.REWRITE: ("rewriter", "rewrite-v1", response_model),
        AITask.SUMMARY: ("summarizer", "summary-v1", response_model),
    }
    return tuple(
        ModelPolicy(
            task,
            settings.ai.provider,
            model,
            prompt,
            1,
            schema,
            settings.ai.temperature,
            settings.ai.max_output_tokens,
            settings.ai.timeout_seconds,
            settings.ai.max_retries,
            settings.ai.confidence_threshold,
            settings.ai.structured_output_mode,
            Decimal(settings.ai.input_cost_per_million),
            Decimal(settings.ai.output_cost_per_million),
        )
        for task, (prompt, schema, model) in prompt_schema.items()
    )
