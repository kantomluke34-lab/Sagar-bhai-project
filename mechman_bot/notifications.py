"""Async meeting reminder and follow-up scheduler."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

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

    async def _send(self, meeting: dict, key: str, body: str, template_name: str = "", language: str = "en_US", mapping: list[str] | None = None, values: dict | None = None) -> None:
        if await self.repository.delivery_exists(meeting["id"], key):
            return
        if template_name:
            templates = await self.repository.list_templates()
            template = next((item for item in templates if item["name"] == template_name and item["language"] == language and item["status"] == "APPROVED"), None)
            if not template:
                raise RuntimeError("Selected reminder template is no longer approved")
            count = max([int(value) for value in re.findall(r"\{\{(\d+)\}\}", template["body"])], default=0)
            mapping = mapping if mapping is not None else ["name"]
            if len(mapping) != count:
                raise RuntimeError("Template variable mapping does not match the approved message")
            available = {"name": meeting["name"], **(values or {})}
            parameters = [str(available.get(key, "")) for key in mapping]
            if any(not value for value in parameters):
                raise RuntimeError("A template variable has no value")
            wa_id = await self.waba.send_template(
                meeting["phone"], template_name, language, parameters
            )
            body = template["body"]
            for index, value in enumerate(parameters, 1):
                body = body.replace(f"{{{{{index}}}}}", value)
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
                try:
                    start = meeting["start_at"].astimezone(ZoneInfo("Asia/Kolkata"))
                    values = {"name": meeting["name"], "date": start.strftime("%d %B %Y"), "time": start.strftime("%I:%M %p"), "minutes": minutes, "days": ""}
                    body = str(settings.get("reminder_template", "")).format(**values)
                    await self._send(
                        meeting,
                        f"reminder:{minutes}",
                        body,
                        str(settings.get("reminder_meta_template", "")),
                        str(settings.get("reminder_meta_language", "en_US")),
                        settings.get("reminder_meta_parameters", ["name"]), values,
                    )
                    sent += 1
                except Exception as exc:
                    LOGGER.exception("Failed to send meeting reminder for %s", meeting["id"])
                    await self.repository.record_notification_failure(meeting, f"reminder:{minutes}", str(settings.get("reminder_template", "")), str(exc))
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
                    try:
                        start = meeting["start_at"].astimezone(ZoneInfo("Asia/Kolkata"))
                        values = {"name": meeting["name"], "date": start.strftime("%d %B %Y"), "time": start.strftime("%I:%M %p"), "minutes": "", "days": days}
                        body = str(settings.get("followup_template", "")).format(**values)
                        await self._send(
                            meeting,
                            f"followup:{days}",
                            body,
                            str(settings.get("followup_meta_template", "")),
                            str(settings.get("followup_meta_language", "en_US")),
                            settings.get("followup_meta_parameters", ["name"]), values,
                        )
                        sent += 1
                    except Exception as exc:
                        LOGGER.exception("Failed to send meeting follow-up for %s", meeting["id"])
                        await self.repository.record_notification_failure(meeting, f"followup:{days}", str(settings.get("followup_template", "")), str(exc))
        return sent

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                LOGGER.exception("Notification scheduler cycle failed")
            await asyncio.sleep(self.interval_seconds)
