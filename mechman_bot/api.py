"""HTTP API for the Mechman meeting CRM."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator

from .auth import create_access_token, current_user_dependency, verify_password
from .config import Settings
from .repository import CRMRepository
from .waba import WABAClient, WABAError

IST = ZoneInfo("Asia/Kolkata")
BUSINESS_START = time(9, 0)
BUSINESS_END = time(18, 30)
MEETING_STATUSES = {"requested", "confirmed", "scheduled", "completed", "cancelled", "no_show"}
LEAD_STAGES = {"new", "qualified", "proposal", "won", "lost"}


class LoginRequest(BaseModel):
    username: str
    password: str


class PublicMeetingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=32)
    email: str = Field(min_length=5, max_length=255)
    meeting_date: date
    start_time: time
    interest: str = Field(default="General enquiry", max_length=255)
    purpose: str = Field(default="Meeting requested through the booking form", max_length=2000)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if not 8 <= len(digits) <= 15:
            raise ValueError("Enter a valid phone number")
        return digits


class MeetingUpdate(BaseModel):
    status: str | None = None
    lead_stage: str | None = None
    assigned_to: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=5000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    meeting_mode: str | None = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in MEETING_STATUSES:
            raise ValueError("Invalid meeting status")
        return value

    @field_validator("lead_stage")
    @classmethod
    def valid_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in LEAD_STAGES:
            raise ValueError("Invalid CRM stage")
        return value


class ManualMessage(BaseModel):
    text: str | None = Field(default=None, max_length=4096)
    template_id: int | None = None
    parameters: list[str] = Field(default_factory=list, max_length=10)


class TemplateDraft(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9_]+$", min_length=3, max_length=512)
    language: str = Field(default="en_US", max_length=20)
    category: Literal["UTILITY", "MARKETING", "AUTHENTICATION"] = "UTILITY"
    header: str | None = Field(default=None, max_length=60)
    body: str = Field(min_length=1, max_length=1024)
    footer: str | None = Field(default=None, max_length=60)
    buttons: list[dict[str, Any]] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def examples_match_body_variables(self) -> TemplateDraft:
        placeholders = [int(value) for value in re.findall(r"\{\{(\d+)\}\}", self.body)]
        expected = list(range(1, max(placeholders, default=0) + 1))
        if sorted(set(placeholders)) != expected:
            raise ValueError("Body variables must be sequential: {{1}}, {{2}}, and so on")
        if len(self.variables) != len(expected):
            raise ValueError("Provide one variable example for each body variable")
        return self


class NotificationSettings(BaseModel):
    reminder_enabled: bool
    reminder_minutes_before: int = Field(ge=15, le=1440)
    reminder_template: str = Field(min_length=1, max_length=4096)
    reminder_meta_template: str = Field(default="", max_length=512)
    followup_enabled: bool
    followup_days: list[int] = Field(min_length=1, max_length=10)
    followup_template: str = Field(min_length=1, max_length=4096)
    followup_meta_template: str = Field(default="", max_length=512)

    @field_validator("followup_days")
    @classmethod
    def valid_days(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 90 for value in values):
            raise ValueError("Follow-up days must be between 1 and 90")
        return sorted(set(values))


def _slot(day: date, start: time, duration: int) -> tuple[datetime, datetime]:
    begins = datetime.combine(day, start, tzinfo=IST)
    ends = begins + timedelta(minutes=duration)
    if day.weekday() == 6 or begins.time() < BUSINESS_START or ends.time() > BUSINESS_END:
        raise HTTPException(status_code=422, detail="Choose Monday-Saturday, 9:00 AM-6:30 PM IST")
    if begins <= datetime.now(IST):
        raise HTTPException(status_code=422, detail="Choose a future meeting time")
    return begins, ends


def build_router(settings: Settings, repository: CRMRepository, waba: WABAClient) -> APIRouter:
    router = APIRouter()
    current_user = current_user_dependency(settings, repository)

    @router.post("/api/auth/login")
    async def login(payload: LoginRequest) -> dict[str, Any]:
        user = await repository.get_user_by_username(payload.username)
        if user is None or not verify_password(payload.password, str(user["password_hash"])):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account disabled")
        return {
            "access_token": create_access_token(int(user["id"]), "admin", settings),
            "token_type": "bearer",
            "user": {key: user[key] for key in ("id", "username", "full_name", "role")},
        }

    @router.get("/api/auth/me")
    async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return {key: user[key] for key in ("id", "username", "full_name", "role")}

    @router.get("/api/public/config")
    async def public_config() -> dict[str, Any]:
        return {
            "company": "Mechman Solutions",
            "address": "256/50, Makarpura GIDC, Vadodara, Gujarat - 390010",
            "timezone": "Asia/Kolkata",
            "business_hours": "Monday-Saturday, 9:00 AM-6:30 PM IST",
            "duration_minutes": settings.meeting_duration_minutes,
        }

    @router.get("/api/public/slots")
    async def available_slots(day: Annotated[date, Query(alias="date")]) -> list[dict[str, str]]:
        if day.weekday() == 6 or day < datetime.now(IST).date():
            return []
        day_start = datetime.combine(day, BUSINESS_START, tzinfo=IST)
        day_end = datetime.combine(day, BUSINESS_END, tzinfo=IST)
        busy = await repository.busy_ranges(day_start, day_end)
        cursor = day_start
        now = datetime.now(IST)
        slots = []
        while cursor + timedelta(minutes=settings.meeting_duration_minutes) <= day_end:
            end = cursor + timedelta(minutes=settings.meeting_duration_minutes)
            occupied = any(cursor < row["end_at"] and row["start_at"] < end for row in busy)
            if cursor > now and not occupied:
                slots.append(
                    {
                        "start_time": cursor.strftime("%H:%M"),
                        "end_time": end.strftime("%H:%M"),
                        "label": cursor.strftime("%-I:%M %p"),
                    }
                )
            cursor += timedelta(minutes=30)
        return slots

    @router.post("/api/public/meetings", status_code=status.HTTP_201_CREATED)
    async def create_public_meeting(payload: PublicMeetingCreate) -> dict[str, Any]:
        begins, ends = _slot(
            payload.meeting_date, payload.start_time, settings.meeting_duration_minutes
        )
        if await repository.busy_ranges(begins, ends):
            raise HTTPException(status_code=409, detail="That slot is no longer available")
        meeting = await repository.create_meeting(
            {
                "name": payload.name,
                "phone": payload.phone,
                "email": payload.email,
                "company": "",
                "interest": payload.interest,
                "purpose": payload.purpose,
                "meeting_mode": "WhatsApp or phone call",
                "start_at": begins,
                "end_at": ends,
                "source": "web_form",
            }
        )
        return {
            "meeting_id": meeting["id"],
            "status": meeting["status"],
            "start_at": begins,
            "end_at": ends,
            "message": "Your meeting request is recorded. The Mechman team will confirm it shortly.",
        }

    @router.get("/api/dashboard/analytics")
    async def analytics(_: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return await repository.analytics()

    @router.get("/api/meetings")
    async def meetings(
        _: dict[str, Any] = Depends(current_user),
        q: str = "",
        meeting_status: Annotated[str, Query(alias="status")] = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, Any]]:
        return await repository.list_meetings(q, meeting_status, date_from, date_to)

    @router.get("/api/meetings/{meeting_id}")
    async def meeting_detail(
        meeting_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.get_meeting(meeting_id)
        if not result:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return result

    @router.patch("/api/meetings/{meeting_id}")
    async def update_meeting(
        meeting_id: int,
        payload: MeetingUpdate,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        result = await repository.update_meeting(
            meeting_id, payload.model_dump(exclude_none=True), str(user["username"])
        )
        if not result:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return result

    @router.get("/api/crm/contacts")
    async def contacts(
        _: dict[str, Any] = Depends(current_user), q: str = ""
    ) -> list[dict[str, Any]]:
        return await repository.list_contacts(q)

    @router.get("/api/crm/contacts/{contact_id}")
    async def contact_detail(
        contact_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.get_contact(contact_id)
        if not result:
            raise HTTPException(status_code=404, detail="Contact not found")
        return result

    @router.get("/api/conversations")
    async def conversations(
        _: dict[str, Any] = Depends(current_user), q: str = ""
    ) -> list[dict[str, Any]]:
        return await repository.list_conversations(q)

    @router.get("/api/conversations/{conversation_id}")
    async def conversation_detail(
        conversation_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.get_conversation(conversation_id)
        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found")
        result["messages"] = await repository.list_messages(conversation_id)
        return result

    @router.post("/api/conversations/{conversation_id}/take-over")
    async def take_over(
        conversation_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.set_takeover(conversation_id, True)
        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return result

    @router.post("/api/conversations/{conversation_id}/return-to-bot")
    async def return_to_bot(
        conversation_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.set_takeover(conversation_id, False)
        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return result

    @router.post("/api/conversations/{conversation_id}/messages")
    async def send_manual_message(
        conversation_id: int,
        payload: ManualMessage,
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        conversation = await repository.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if not conversation["is_taken_over"]:
            raise HTTPException(
                status_code=409, detail="Take over this conversation before replying"
            )
        if payload.template_id:
            template = await repository.get_template(payload.template_id)
            if not template or template["status"] != "APPROVED":
                raise HTTPException(status_code=422, detail="Choose an approved Meta template")
            expected_parameters = max(
                [int(value) for value in re.findall(r"\{\{(\d+)\}\}", template["body"])],
                default=0,
            )
            if len(payload.parameters) != expected_parameters:
                raise HTTPException(
                    status_code=422,
                    detail=f"This template requires {expected_parameters} parameter value(s)",
                )
            wa_id = await waba.send_template(
                conversation["phone"], template["name"], template["language"], payload.parameters
            )
            body = template["body"]
            for index, value in enumerate(payload.parameters, 1):
                body = body.replace(f"{{{{{index}}}}}", value)
            message_type = "template"
        elif payload.text:
            if not await repository.within_service_window(conversation_id):
                raise HTTPException(
                    status_code=409,
                    detail="The 24-hour service window is closed. Send an approved Meta template instead.",
                )
            wa_id = await waba.send_text(conversation["phone"], payload.text)
            body = payload.text
            message_type = "text"
        else:
            raise HTTPException(status_code=422, detail="Message text or template is required")
        message = await repository.add_message(
            conversation_id,
            direction="outbound",
            body=body,
            sender="admin",
            wa_message_id=wa_id,
            message_type=message_type,
            status="accepted",
        )
        return message or {"wa_message_id": wa_id}

    @router.get("/api/templates")
    async def templates(
        _: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        return await repository.list_templates()

    @router.post("/api/templates", status_code=status.HTTP_201_CREATED)
    async def create_template(
        payload: TemplateDraft, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        return await repository.create_template({**payload.model_dump(), "status": "DRAFT"})

    @router.put("/api/templates/{template_id}")
    async def update_template(
        template_id: int,
        payload: TemplateDraft,
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        current = await repository.get_template(template_id)
        if not current:
            raise HTTPException(status_code=404, detail="Template not found")
        if current["status"] not in {"DRAFT", "REJECTED"}:
            raise HTTPException(
                status_code=409,
                detail="Approved or pending templates cannot be edited; create a new version",
            )
        result = await repository.update_template(
            template_id, {**payload.model_dump(), "status": "DRAFT", "rejection_reason": None}
        )
        return result or {}

    @router.post("/api/templates/{template_id}/submit")
    async def submit_template(
        template_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        template = await repository.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        if template["status"] not in {"DRAFT", "REJECTED"}:
            raise HTTPException(status_code=409, detail="Template is already submitted")
        try:
            meta = await waba.submit_template(template)
        except WABAError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        result = await repository.update_template(
            template_id,
            {
                "status": "PENDING",
                "meta_template_id": str(meta.get("id", "")),
                "rejection_reason": None,
            },
        )
        return result or {}

    @router.post("/api/templates/sync")
    async def sync_templates(_: dict[str, Any] = Depends(current_user)) -> dict[str, int]:
        try:
            remote = await waba.list_meta_templates()
        except WABAError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        for item in remote:
            components = {
                str(component.get("type", "")).upper(): component
                for component in item.get("components", [])
            }
            body_component = components.get("BODY", {})
            body_examples = body_component.get("example", {}).get("body_text", [[]])
            variable_examples = body_examples[0] if body_examples else []
            await repository.update_template_from_meta(
                str(item.get("name", "")),
                str(item.get("language", "")),
                {
                    "status": str(item.get("status", "PENDING")),
                    "meta_template_id": str(item.get("id", "")),
                    "category": str(item.get("category", "UTILITY")),
                    "header": components.get("HEADER", {}).get("text"),
                    "body": str(body_component.get("text", "Imported from Meta")),
                    "footer": components.get("FOOTER", {}).get("text"),
                    "buttons": components.get("BUTTONS", {}).get("buttons", []),
                    "variables": variable_examples,
                    "rejection_reason": item.get("rejected_reason"),
                    "synced_at": datetime.now(IST),
                },
            )
        return {"synced": len(remote)}

    @router.get("/api/settings/notifications")
    async def notification_settings(
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        return await repository.notification_settings()

    @router.put("/api/settings/notifications")
    async def save_notification_settings(
        payload: NotificationSettings, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        return await repository.save_notification_settings(payload.model_dump())

    @router.get("/api/settings/notifications/deliveries")
    async def notification_deliveries(
        _: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        return await repository.list_deliveries()

    @router.get("/api/waba/status")
    async def waba_status(_: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return {
            "configured": waba.configured,
            "phone_number_id": settings.meta_phone_number_id,
            "waba_id": settings.meta_waba_id,
            "api_version": settings.meta_api_version,
            "webhook_verification_configured": bool(settings.meta_webhook_verify_token),
            "signature_validation_configured": bool(settings.meta_app_secret),
        }

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return router
