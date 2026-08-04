"""Safe advisory routing over the provider-neutral runtime."""

from enum import StrEnum
from uuid import UUID

from business_assistant.application.telegram import TelegramIdentity

from .models import (
    AICompletionStatus,
    AIRequest,
    AIResult,
    AITask,
    Intent,
    IntentResult,
    SuggestedAction,
)
from .runtime import AIRuntime


class AdvisoryRoute(StrEnum):
    HOME = "home"
    CATALOG = "catalog"
    HOURS = "hours"
    KNOWLEDGE = "knowledge"
    FALLBACK = "fallback"


class AITextRouter:
    def __init__(self, runtime: AIRuntime) -> None:
        self._runtime = runtime

    async def route(
        self, identity: TelegramIdentity, text: str, *, correlation_id: UUID
    ) -> AdvisoryRoute:
        execution = await self._runtime.execute(
            AIRequest(
                identity.tenant_id,
                identity.conversation_id,
                correlation_id,
                AITask.INTENT,
                text,
            )
        )
        if execution.status is not AICompletionStatus.SUCCESS or not isinstance(
            execution.result, IntentResult
        ):
            return AdvisoryRoute.FALLBACK
        return {
            SuggestedAction.SHOW_HOME: AdvisoryRoute.HOME,
            SuggestedAction.SHOW_CATALOG: AdvisoryRoute.CATALOG,
            SuggestedAction.SHOW_HOURS: AdvisoryRoute.HOURS,
            SuggestedAction.ANSWER_KNOWLEDGE: AdvisoryRoute.KNOWLEDGE,
        }.get(execution.result.suggested_action, AdvisoryRoute.FALLBACK)


class AdvisoryRoutingValidator:
    """Business gate permitting only semantically matched read-only presentation routes."""

    def validate(self, request: AIRequest, result: AIResult) -> None:
        if request.task is not AITask.INTENT:
            return
        if not isinstance(result, IntentResult):
            raise ValueError("Intent routing requires an intent result")
        allowed = {
            SuggestedAction.SHOW_HOME: {Intent.GREETING, Intent.HELP, Intent.LOCATION_CONTACT},
            SuggestedAction.SHOW_CATALOG: {
                Intent.SERVICE_DISCOVERY,
                Intent.SERVICE_DETAIL,
            },
            SuggestedAction.SHOW_HOURS: {Intent.BUSINESS_HOURS},
            SuggestedAction.ANSWER_KNOWLEDGE: {Intent.FAQ_KNOWLEDGE},
        }
        if (
            result.suggested_action in allowed
            and result.intent not in allowed[result.suggested_action]
        ):
            raise ValueError("AI advisory route is inconsistent with the classified intent")
