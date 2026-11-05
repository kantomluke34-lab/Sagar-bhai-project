"""HTTP API for the Mechman meeting CRM."""

from __future__ import annotations

import hashlib
import re
import string
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, field_validator, model_validator

from .auth import create_access_token, current_user_dependency, hash_password, verify_password
from .campaigns import infer_media_type, normalize_phone, parse_recipient_file, render_parameters
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


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)

    @model_validator(mode="after")
    def passwords_match(self) -> PasswordChange:
        if self.new_password != self.confirm_password:
            raise ValueError("New passwords do not match")
        if self.new_password == self.current_password:
            raise ValueError("New password must be different from the current password")
        return self


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
        if len(digits) == 10 and digits[0] in "6789":
            digits = "91" + digits
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


class AdminMeetingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    company: str = Field(default="", max_length=200)
    interest: str = Field(default="General enquiry", max_length=255)
    purpose: str = Field(default="", max_length=2000)
    meeting_mode: str = Field(default="Phone call", max_length=100)
    start_at: datetime
    end_at: datetime
    status: Literal["requested", "confirmed", "scheduled", "completed", "cancelled", "no_show"] = "scheduled"
    lead_stage: Literal["new", "qualified", "proposal", "won", "lost"] = "new"

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str) -> str:
        return PublicMeetingCreate.normalize_phone(value)

    @model_validator(mode="after")
    def valid_times(self) -> AdminMeetingCreate:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None or self.end_at <= self.start_at:
            raise ValueError("Choose a valid start and end time with a timezone")
        return self


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
    header_format: Literal["NONE", "TEXT", "IMAGE", "VIDEO", "DOCUMENT"] = "NONE"
    header_sample_handle: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def examples_match_body_variables(self) -> TemplateDraft:
        placeholders = [int(value) for value in re.findall(r"\{\{(\d+)\}\}", self.body)]
        expected = list(range(1, max(placeholders, default=0) + 1))
        if sorted(set(placeholders)) != expected:
            raise ValueError("Body variables must be sequential: {{1}}, {{2}}, and so on")
        if len(self.variables) != len(expected):
            raise ValueError("Provide one variable example for each body variable")
        if self.header_format == "TEXT" and not self.header:
            raise ValueError("Enter header text or choose no header")
        if self.header_format in {"IMAGE", "VIDEO", "DOCUMENT"}:
            if not self.header_sample_handle:
                raise ValueError("Upload a sample file for the media header")
            if self.header:
                raise ValueError("Media headers cannot include header text")
        return self


class RecipientListDraft(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    list_type: Literal["static"] = "static"
    member_ids: list[int] = Field(min_length=1, max_length=10_000)


class CampaignRecipientInput(BaseModel):
    phone: str
    name: str | None = Field(default=None, max_length=160)
    variables: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not normalized:
            raise ValueError("Enter a 7-15 digit international phone number")
        return normalized


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    template_id: int
    source_type: Literal["csv", "paste", "list"]
    list_id: int | None = None
    expected_recipient_count: int | None = Field(default=None, ge=1)
    recipients: list[CampaignRecipientInput] = Field(default_factory=list, max_length=10_000)
    consent_confirmed: bool = False
    consent_source: str | None = Field(default=None, max_length=120)
    consent_captured_at: datetime | None = None
    schedule_type: Literal["once", "daily", "weekly"] = "once"
    scheduled_at: datetime
    parameter_mapping: list[str] = Field(default_factory=list, max_length=20)
    asset_id: int | None = None
    throttle_seconds: float = Field(default=1, ge=0, le=10)

    @model_validator(mode="after")
    def validate_source(self) -> CampaignCreate:
        if self.source_type == "list" and not self.list_id:
            raise ValueError("Choose a CRM audience")
        if self.source_type in {"csv", "paste"}:
            if not self.recipients:
                raise ValueError("Add at least one valid recipient")
            if not self.consent_confirmed or not self.consent_source or not self.consent_captured_at:
                raise ValueError("Recipients require consent confirmation, source, and date")
        return self


class ContactConsentUpdate(BaseModel):
    status: Literal["unknown", "opted_in", "opted_out"]
    source: str | None = Field(default=None, max_length=120)
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def require_opt_in_evidence(self) -> ContactConsentUpdate:
        if self.status == "opted_in" and (not self.source or not self.captured_at):
            raise ValueError("Opt-in requires a consent source and captured date")
        return self


class ContactInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=200)
    designation: str | None = Field(default=None, max_length=160)
    city: str | None = Field(default=None, max_length=120)
    source: str = Field(default="manual", max_length=40)
    lead_stage: Literal["new", "qualified", "proposal", "won", "lost"] = "new"
    lead_status: Literal["open", "completed"] = "open"

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str) -> str:
        return PublicMeetingCreate.normalize_phone(value)


class ContactImport(BaseModel):
    rows: list[ContactInput] = Field(min_length=1, max_length=10_000)


class NotificationSettings(BaseModel):
    reminder_enabled: bool
    reminder_minutes_before: int = Field(ge=15, le=1440)
    reminder_template: str = Field(min_length=1, max_length=4096)
    reminder_meta_template: str = Field(default="", max_length=512)
    reminder_meta_language: str = Field(default="en_US", max_length=20)
    reminder_meta_parameters: list[Literal["name", "date", "time", "minutes", "days"]] = Field(default_factory=lambda: ["name"], max_length=20)
    followup_enabled: bool
    followup_days: list[int] = Field(min_length=1, max_length=10)
    followup_template: str = Field(min_length=1, max_length=4096)
    followup_meta_template: str = Field(default="", max_length=512)
    followup_meta_language: str = Field(default="en_US", max_length=20)
    followup_meta_parameters: list[Literal["name", "date", "time", "minutes", "days"]] = Field(default_factory=lambda: ["name"], max_length=20)

    @field_validator("followup_days")
    @classmethod
    def valid_days(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 90 for value in values):
            raise ValueError("Follow-up days must be between 1 and 90")
        return sorted(set(values))

    @field_validator("reminder_template", "followup_template")
    @classmethod
    def valid_message_placeholders(cls, value: str) -> str:
        try:
            parts = list(string.Formatter().parse(value))
        except ValueError as exc:
            raise ValueError("Use matching braces around placeholders") from exc
        allowed = {"name", "date", "time", "minutes", "days"}
        if any(field is not None and (field not in allowed or spec or conversion) for _, field, spec, conversion in parts):
            raise ValueError("Use only the listed message placeholders")
        return value


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

    @router.post("/api/auth/change-password")
    async def change_password(
        payload: PasswordChange, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, str]:
        if not verify_password(payload.current_password, str(user["password_hash"])):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        changed = await repository.update_user_password(
            int(user["id"]), hash_password(payload.new_password)
        )
        if not changed:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"message": "Password changed successfully"}

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
        try:
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
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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

    @router.post("/api/meetings", status_code=status.HTTP_201_CREATED)
    async def create_admin_meeting(payload: AdminMeetingCreate, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            meeting = await repository.create_meeting({**payload.model_dump(), "source": "admin"}, str(user["username"]))
            return await repository.get_meeting(meeting["id"]) or meeting
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
        try:
            result = await repository.update_meeting(
                meeting_id, payload.model_dump(exclude_none=True), str(user["username"])
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not result:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return result

    @router.get("/api/crm/contacts")
    async def contacts(
        _: dict[str, Any] = Depends(current_user), q: str = "",
        page: int | None = Query(default=None, ge=1), page_size: int = Query(default=50, ge=1, le=100),
        consent_status: Literal["opted_in"] | None = None,
    ) -> Any:
        return await repository.list_contacts(q, page, page_size, consent_status)

    @router.post("/api/crm/contacts", status_code=status.HTTP_201_CREATED)
    async def create_contact(payload: ContactInput, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return await repository.save_contact(payload.model_dump()) or {}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/crm/contacts/import")
    async def import_contacts(payload: ContactImport, _: dict[str, Any] = Depends(current_user)) -> dict[str, int]:
        try:
            return await repository.import_contacts([row.model_dump() for row in payload.rows])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.put("/api/crm/contacts/{contact_id}")
    async def update_contact(contact_id: int, payload: ContactInput, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            result = await repository.save_contact(payload.model_dump(), contact_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not result:
            raise HTTPException(status_code=404, detail="Contact not found")
        return result

    @router.get("/api/crm/contacts/{contact_id}")
    async def contact_detail(
        contact_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.get_contact(contact_id)
        if not result:
            raise HTTPException(status_code=404, detail="Contact not found")
        return result

    @router.put("/api/crm/contact-consent/{contact_id}")
    async def update_contact_consent(
        contact_id: int,
        payload: ContactConsentUpdate,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        contact = await repository.get_contact(contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        await repository.set_contact_consent(
            contact_id,
            payload.status,
            payload.source,
            payload.captured_at,
            {"updated_by": user["username"], "method": "crm"},
        )
        return (await repository.get_contact(contact_id)) or {}

    @router.get("/api/audiences")
    async def audiences(_: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return await repository.list_recipient_lists()

    @router.post("/api/audiences", status_code=status.HTTP_201_CREATED)
    async def create_audience(
        payload: RecipientListDraft, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        if not await repository.members_have_consent(payload.member_ids):
            raise HTTPException(status_code=422, detail="Choose contacts who opted in to WhatsApp messages")
        try:
            return await repository.create_recipient_list(payload.model_dump())
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=409, detail="Audience name already exists") from exc
            raise

    @router.put("/api/audiences/{list_id}")
    async def update_audience(
        list_id: int,
        payload: RecipientListDraft,
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        if not await repository.members_have_consent(payload.member_ids, list_id):
            raise HTTPException(status_code=422, detail="Choose contacts who opted in to WhatsApp messages")
        result = await repository.update_recipient_list(list_id, payload.model_dump())
        if not result:
            raise HTTPException(status_code=404, detail="Audience not found")
        return result

    @router.delete(
        "/api/audiences/{list_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
    )
    async def delete_audience(
        list_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> None:
        if not await repository.delete_recipient_list(list_id):
            raise HTTPException(status_code=404, detail="Audience not found")

    @router.get("/api/conversations")
    async def conversations(
        _: dict[str, Any] = Depends(current_user), q: str = ""
    ) -> list[dict[str, Any]]:
        return await repository.list_conversations(q)

    @router.get("/api/conversations/{conversation_id}")
    async def conversation_detail(
        conversation_id: int, _: dict[str, Any] = Depends(current_user),
        message_offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        result = await repository.get_conversation(conversation_id)
        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = await repository.list_messages(conversation_id, limit=101, offset=message_offset)
        result["has_more_messages"] = len(messages) > 100
        result["messages"] = messages[-100:]
        result["service_window_open"] = await repository.within_service_window(conversation_id)
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
            if template.get("category") == "MARKETING" and not await repository.contact_opted_in(conversation["contact_id"], conversation["phone"]):
                raise HTTPException(status_code=409, detail="This contact has not opted in to campaign messages")
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
                    "header_format": str(components.get("HEADER", {}).get("format", "NONE")),
                    "body": str(body_component.get("text", "Imported from Meta")),
                    "footer": components.get("FOOTER", {}).get("text"),
                    "buttons": components.get("BUTTONS", {}).get("buttons", []),
                    "variables": variable_examples,
                    "rejection_reason": item.get("rejected_reason"),
                    "synced_at": datetime.now(IST),
                },
            )
        return {"synced": len(remote)}

    @router.post("/api/campaigns/import/preview")
    async def preview_campaign_import(
        upload: UploadFile = File(...), _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        content = await upload.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Recipient file is limited to 8 MB")
        try:
            return parse_recipient_file(upload.filename or "recipients.csv", content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/campaigns/media", status_code=status.HTTP_201_CREATED)
    async def upload_campaign_media(
        upload: UploadFile = File(...), _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=422, detail="Uploaded media file is empty")
        media_type = infer_media_type(upload.content_type or "application/octet-stream")
        if not media_type:
            raise HTTPException(status_code=422, detail="Use an image, video, PDF, DOC, or DOCX")
        type_limit = {
            "IMAGE": 5 * 1024 * 1024,
            "VIDEO": 16 * 1024 * 1024,
            "DOCUMENT": settings.max_media_bytes,
        }.get(media_type or "", 0)
        if len(content) > type_limit:
            raise HTTPException(
                status_code=413,
                detail=f"{str(media_type).title()} is limited to {type_limit // (1024 * 1024)} MB",
            )
        mime_type = upload.content_type or "application/octet-stream"
        suffix = Path(upload.filename or "media").suffix.lower()[:10]
        storage_name = f"{uuid.uuid4().hex}{suffix}"
        media_root = Path(settings.media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        (media_root / storage_name).write_bytes(content)
        return await repository.save_media_asset(
            {
                "original_name": Path(upload.filename or "media").name[:255],
                "storage_name": storage_name,
                "mime_type": mime_type,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    @router.post("/api/templates/media-sample", status_code=status.HTTP_201_CREATED)
    async def upload_template_media_sample(
        upload: UploadFile = File(...), _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, str]:
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=422, detail="Sample file is empty")
        mime_type = upload.content_type or "application/octet-stream"
        allowed_types = {
            "image/jpeg": "IMAGE",
            "image/png": "IMAGE",
            "video/mp4": "VIDEO",
            "application/pdf": "DOCUMENT",
        }
        media_type = allowed_types.get(mime_type)
        if media_type is None:
            raise HTTPException(status_code=422, detail="Use a JPG, PNG, MP4, or PDF sample")
        type_limit = {
            "IMAGE": 5 * 1024 * 1024,
            "VIDEO": 16 * 1024 * 1024,
            "DOCUMENT": settings.max_media_bytes,
        }[media_type]
        if len(content) > type_limit:
            raise HTTPException(
                status_code=413,
                detail=f"{media_type.title()} is limited to {type_limit // (1024 * 1024)} MB",
            )
        try:
            handle = await waba.upload_template_header_sample(
                content, mime_type, upload.filename or "sample"
            )
        except WABAError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "header_format": media_type,
            "header_sample_handle": handle,
            "original_name": Path(upload.filename or "sample").name[:255],
        }

    @router.get("/api/campaigns")
    async def campaigns(_: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return await repository.list_campaigns()

    @router.get("/api/campaigns/{campaign_id}")
    async def campaign_detail(
        campaign_id: int, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        result = await repository.get_campaign(campaign_id)
        if not result:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return result

    @router.post("/api/campaigns", status_code=status.HTTP_201_CREATED)
    async def create_campaign(
        payload: CampaignCreate, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        template = await repository.get_template(payload.template_id)
        if not template or str(template.get("status", "")).upper() != "APPROVED":
            raise HTTPException(status_code=422, detail="Choose an approved Meta template")
        required = max(
            [int(value) for value in re.findall(r"\{\{(\d+)\}\}", template["body"])],
            default=0,
        )
        if len(payload.parameter_mapping) != required:
            raise HTTPException(
                status_code=422,
                detail=f"Template requires {required} mapped variable(s)",
            )
        header_format = str(template.get("header_format") or "NONE").upper()
        if header_format in {"IMAGE", "VIDEO", "DOCUMENT"}:
            if not payload.asset_id:
                raise HTTPException(status_code=422, detail=f"{header_format.title()} template requires media")
            asset = await repository.get_media_asset(payload.asset_id)
            if not asset or infer_media_type(asset["mime_type"]) != header_format:
                raise HTTPException(status_code=422, detail=f"Upload matching {header_format.lower()} media")
        elif payload.asset_id:
            raise HTTPException(status_code=422, detail="Selected template does not accept media")

        if payload.source_type == "list":
            rows = await repository.resolve_recipient_list(int(payload.list_id or 0))
            recipients = [
                {
                    "contact_id": row["id"],
                    "phone": row["phone"],
                    "name": row["name"],
                    "variables": row,
                    "consent_source": row["consent_source"],
                    "consent_captured_at": row["consent_captured_at"],
                }
                for row in rows
            ]
            if (
                payload.expected_recipient_count is not None
                and len(recipients) != payload.expected_recipient_count
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Audience changed. Review the recipient count and schedule again.",
                )
        else:
            recipients = [
                {
                    "phone": row.phone,
                    "name": row.name or row.variables.get("name"),
                    "variables": row.variables,
                    "consent_source": payload.consent_source,
                    "consent_captured_at": payload.consent_captured_at,
                    "consent_evidence": {"method": "csv_confirmation", "confirmed_by": user["username"]},
                }
                for row in payload.recipients
            ]
        if not recipients:
            raise HTTPException(status_code=422, detail="Audience contains no opted-in recipients")
        for recipient in recipients:
            try:
                render_parameters(payload.parameter_mapping, recipient["variables"])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Recipient data is incomplete: {exc}") from exc
        scheduled_at = payload.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=IST)
        if scheduled_at <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Choose a future campaign time")
        try:
            return await repository.create_campaign(
            {
                "name": payload.name,
                "template_id": payload.template_id,
                "list_id": payload.list_id,
                "asset_id": payload.asset_id,
                "source_type": payload.source_type,
                "schedule_type": payload.schedule_type,
                "scheduled_at": scheduled_at.astimezone(UTC),
                "timezone": "Asia/Kolkata",
                "status": "scheduled",
                "parameter_mapping": payload.parameter_mapping,
                "throttle_seconds": payload.throttle_seconds,
                "created_by": str(user["username"]),
            },
            recipients,
            )
        except ValueError as exc:
            code = 409 if str(exc).startswith("Audience changed.") else 422
            raise HTTPException(status_code=code, detail=str(exc)) from exc

    @router.post("/api/campaigns/{campaign_id}/{action}")
    async def campaign_action(
        campaign_id: int,
        action: Literal["pause", "resume", "cancel"],
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            result = await repository.set_campaign_status(campaign_id, action)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not result:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return result

    @router.post(
        "/api/campaigns/{campaign_id}/deliveries/retry-failed",
        status_code=status.HTTP_201_CREATED,
    )
    async def retry_failed_campaign(
        campaign_id: int, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        try:
            return await repository.retry_failed_campaign(campaign_id, str(user["username"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/settings/notifications")
    async def notification_settings(
        _: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        return await repository.notification_settings()

    @router.put("/api/settings/notifications")
    async def save_notification_settings(
        payload: NotificationSettings, _: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        templates = await repository.list_templates()
        for prefix in ("reminder", "followup"):
            name = getattr(payload, f"{prefix}_meta_template")
            if not name:
                continue
            language = getattr(payload, f"{prefix}_meta_language")
            template = next((item for item in templates if item["name"] == name and item["language"] == language and item["status"] == "APPROVED"), None)
            if not template or template.get("header_format") in {"IMAGE", "VIDEO", "DOCUMENT"}:
                raise HTTPException(status_code=422, detail=f"Choose an approved text-only {prefix} template")
            count = max([int(value) for value in re.findall(r"\{\{(\d+)\}\}", template["body"])], default=0)
            if len(getattr(payload, f"{prefix}_meta_parameters")) != count:
                raise HTTPException(status_code=422, detail=f"Map all {prefix} template variables")
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
