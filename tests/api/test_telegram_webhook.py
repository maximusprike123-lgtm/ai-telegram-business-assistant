import logging
from uuid import uuid4

from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from business_assistant.application.telegram import TelegramBotBinding
from business_assistant.domain.shared import TenantId
from business_assistant.presentation.telegram import (
    TelegramWebhookServices,
    install_telegram_webhook,
)


class FakeDispatcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.updates = []

    async def feed_update(self, bot, update, **kwargs):
        if self.fail:
            raise RuntimeError("provider detail must not be returned")
        self.updates.append((bot.id, update.update_id, kwargs["correlation_id"]))
        return "processed"


def webhook_client(*, fail: bool = False, max_bytes: int = 1024):
    app = FastAPI()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.correlation_id = "request-123"
        return await call_next(request)

    bot = Bot("42:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    dispatcher = FakeDispatcher(fail=fail)
    install_telegram_webhook(
        app,
        TelegramWebhookServices(
            dispatcher,  # type: ignore[arg-type]
            bot,
            TelegramBotBinding(42, TenantId(uuid4())),
            "header_secret",  # pragma: allowlist secret
            "configured_path_value",  # pragma: allowlist secret
            max_bytes,
            logging.getLogger("test.webhook"),
        ),
    )
    return TestClient(app), dispatcher, bot


def auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": "header_secret",  # pragma: allowlist secret
    }


def test_webhook_authenticates_path_and_header_before_parsing() -> None:
    client, _, bot = webhook_client()
    try:
        response = client.post(
            "/api/v1/webhooks/telegram/configured_path_value", json={"update_id": 1}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "telegram.webhook_authentication_failed"
        response = client.post(
            "/api/v1/webhooks/telegram/unknown", json={"update_id": 1}, headers=auth_headers()
        )
        assert response.status_code == 404
        assert response.json()["code"] == "telegram.bot_mapping_not_found"
    finally:
        client.close()
        import asyncio

        asyncio.run(bot.session.close())


def test_webhook_validates_content_type_size_json_and_update_schema() -> None:
    client, _, bot = webhook_client(max_bytes=64)
    url = "/api/v1/webhooks/telegram/configured_path_value"
    try:
        response = client.post(
            url,
            content=b"{}",
            headers={
                "Content-Type": "text/plain",
                "X-Telegram-Bot-Api-Secret-Token": "header_secret",
            },
        )
        assert response.status_code == 415
        response = client.post(url, content=b"{" + b"x" * 100, headers=auth_headers())
        assert response.status_code == 413
        response = client.post(url, content=b"not-json", headers=auth_headers())
        assert response.status_code == 400
        assert response.json()["code"] == "telegram.update_invalid"
        response = client.post(url, json={"message": {}}, headers=auth_headers())
        assert response.status_code == 400
    finally:
        client.close()
        import asyncio

        asyncio.run(bot.session.close())


def test_webhook_processes_valid_update_and_returns_retryable_safe_failure() -> None:
    url = "/api/v1/webhooks/telegram/configured_path_value"
    client, dispatcher, bot = webhook_client()
    try:
        response = client.post(url, json={"update_id": 7}, headers=auth_headers())
        assert response.status_code == 200
        assert response.json() == {"status": "processed"}
        assert dispatcher.updates == [(42, 7, "request-123")]
        assert "configured_path_value" not in str(client.get("/openapi.json").json())
    finally:
        client.close()
        import asyncio

        asyncio.run(bot.session.close())

    failing, _, failing_bot = webhook_client(fail=True)
    try:
        response = failing.post(url, json={"update_id": 8}, headers=auth_headers())
        assert response.status_code == 503
        assert response.json()["code"] == "telegram.processing_unavailable"
        assert "provider detail" not in response.text
    finally:
        failing.close()
        import asyncio

        asyncio.run(failing_bot.session.close())
