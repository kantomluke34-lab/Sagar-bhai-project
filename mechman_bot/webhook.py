"""Meta webhook verification and event processing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from .cam_assistant import respond
from .config import Settings
from .repository import CRMRepository
from .waba import WABAClient

LOGGER = logging.getLogger(__name__)


def _message_text(message: dict[str, Any]) -> str:
    kind = message.get("type", "")
    if kind == "text":
        return str(message.get("text", {}).get("body", ""))
    if kind == "button":
        return str(message.get("button", {}).get("text", ""))
    if kind == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return str(reply.get("title") or reply.get("id") or "")
    if kind in {"image", "video", "document", "audio"}:
        return str(message.get(kind, {}).get("caption") or f"[{kind}]")
    return f"[{kind or 'unsupported'}]"


class WebhookProcessor:
    def __init__(self, settings: Settings, repository: CRMRepository, waba: WABAClient) -> None:
        self.settings = settings
        self.repository = repository
        self.waba = waba

    async def process(self, payload: dict[str, Any]) -> None:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                await self._process_statuses(value.get("statuses", []))
                await self._process_messages(value)

    async def process_safely(self, payload: dict[str, Any]) -> None:
        try:
            await self.process(payload)
        except Exception:
            LOGGER.exception(
                "webhook_processing_failed",
                extra={"event": "webhook_processing_failed"},
            )

    async def _process_statuses(self, statuses: list[dict[str, Any]]) -> None:
        for status in statuses:
            if status.get("id") and status.get("status"):
                errors = status.get("errors") or []
                first_error = errors[0] if errors else {}
                detail = first_error.get("error_data", {}).get("details")
                error = detail or first_error.get("message") or first_error.get("title")
                await self.repository.update_message_status(
                    str(status["id"]), str(status["status"]), str(error) if error else None
                )

    async def _process_messages(self, value: dict[str, Any]) -> None:
        contacts = {
            str(item.get("wa_id", "")): str(item.get("profile", {}).get("name", ""))
            for item in value.get("contacts", [])
        }
        for message in value.get("messages", []):
            phone = str(message.get("from", ""))
            if not phone:
                continue
            conversation = await self.repository.upsert_conversation(phone, contacts.get(phone, ""))
            timestamp = datetime.fromtimestamp(int(message.get("timestamp", "0")), UTC)
            body = _message_text(message)
            inserted = await self.repository.add_message(
                conversation["id"],
                direction="inbound",
                body=body,
                sender="customer",
                wa_message_id=str(message.get("id", "")),
                message_type=str(message.get("type", "text")),
                status="received",
                metadata=message,
                occurred_at=timestamp,
            )
            if inserted is None or conversation.get("is_taken_over"):
                continue
            reply = respond(
                conversation.get("bot_state"),
                body,
                booking_url=self.settings.public_booking_url,
                display_name=contacts.get(phone, ""),
            )
            await self.repository.save_bot_state(conversation["id"], reply.state)
            for outbound in reply.messages:
                wa_id = await self.waba.send_text(phone, outbound)
                await self.repository.add_message(
                    conversation["id"],
                    direction="outbound",
                    body=outbound,
                    sender="bot",
                    wa_message_id=wa_id,
                    status="accepted",
                )


def build_webhook_router(
    settings: Settings, processor: WebhookProcessor, waba: WABAClient
) -> APIRouter:
    router = APIRouter(prefix="/webhook", tags=["waba-webhook"])

    @router.get("")
    async def verify_webhook(
        mode: str = Query("", alias="hub.mode"),
        verify_token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> Response:
        if mode != "subscribe" or not settings.meta_webhook_verify_token:
            raise HTTPException(status_code=403, detail="Webhook verification is not configured")
        if verify_token != settings.meta_webhook_verify_token:
            raise HTTPException(status_code=403, detail="Invalid verification token")
        return Response(content=challenge, media_type="text/plain")

    @router.post("")
    async def receive_webhook(
        request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, str]:
        body = await request.body()
        if not waba.validate_signature(body, request.headers.get("X-Hub-Signature-256")):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        payload = await request.json()
        background_tasks.add_task(processor.process_safely, payload)
        return {"status": "accepted"}

    return router
