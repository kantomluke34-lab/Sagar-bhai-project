"""Async meeting reminder and follow-up scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from .repository import CRMRepository
from .waba import WABAClient

LOGGER = logging.getLogger(__name__)


class NotificationScheduler:
    def __init__(
        self, repository: CRMRepository, waba: WABAClient, interval_seconds: int = 30
    ) -> None:
        self.repository = repository
        self.waba = waba
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run(), name="meeting-notifications")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _send(self, meeting: dict, key: str, body: str, template_name: str = "") -> None:
        if await self.repository.delivery_exists(meeting["id"], key):
            return
        if template_name:
            wa_id = await self.waba.send_template(
                meeting["phone"], template_name, "en_US", [meeting["name"]]
            )
        else:
            conversation_id = meeting.get("conversation_id")
            if not conversation_id or not await self.repository.within_service_window(
                int(conversation_id)
            ):
                raise RuntimeError(
                    "An approved Meta template is required outside the 24-hour service window"
                )
            wa_id = await self.waba.send_text(meeting["phone"], body)
        await self.repository.add_delivery(
            meeting_id=meeting["id"],
            notification_key=key,
            recipient=meeting["phone"],
            message=body,
            status="accepted",
            wa_message_id=wa_id,
        )
        if meeting.get("conversation_id"):
            await self.repository.add_message(
                meeting["conversation_id"],
                direction="outbound",
                body=body,
                sender="scheduler",
                wa_message_id=wa_id,
                message_type="template" if template_name else "text",
                status="accepted",
            )

    async def run_once(self, now: datetime | None = None) -> int:
        if not self.waba.configured:
            return 0
        now = now or datetime.now(UTC)
        settings = await self.repository.notification_settings()
        sent = 0
        if settings.get("reminder_enabled"):
            minutes = int(settings.get("reminder_minutes_before", 60))
            target = now + timedelta(minutes=minutes)
            candidates = await self.repository.notification_candidates(
                target - timedelta(seconds=self.interval_seconds),
                target + timedelta(seconds=self.interval_seconds),
            )
            for meeting in candidates:
                if meeting["status"] not in {"confirmed", "scheduled"}:
                    continue
                body = str(settings.get("reminder_template", "")).format(
                    name=meeting["name"],
                    date=meeting["start_at"].strftime("%d %B %Y"),
                    time=meeting["start_at"].strftime("%I:%M %p"),
                    minutes=minutes,
                )
                try:
                    await self._send(
                        meeting,
                        f"reminder:{minutes}",
                        body,
                        str(settings.get("reminder_meta_template", "")),
                    )
                    sent += 1
                except Exception:
                    LOGGER.exception("Failed to send meeting reminder for %s", meeting["id"])
        if settings.get("followup_enabled"):
            for days in settings.get("followup_days", [1, 3]):
                target = now - timedelta(days=int(days))
                candidates = await self.repository.notification_candidates(
                    target - timedelta(seconds=self.interval_seconds),
                    target + timedelta(seconds=self.interval_seconds),
                )
                for meeting in candidates:
                    if meeting["status"] not in {"confirmed", "scheduled", "completed"}:
                        continue
                    body = str(settings.get("followup_template", "")).format(
                        name=meeting["name"],
                        date=meeting["start_at"].strftime("%d %B %Y"),
                        days=days,
                    )
                    try:
                        await self._send(
                            meeting,
                            f"followup:{days}",
                            body,
                            str(settings.get("followup_meta_template", "")),
                        )
                        sent += 1
                    except Exception:
                        LOGGER.exception("Failed to send meeting follow-up for %s", meeting["id"])
        return sent

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                LOGGER.exception("Notification scheduler cycle failed")
            await asyncio.sleep(self.interval_seconds)
