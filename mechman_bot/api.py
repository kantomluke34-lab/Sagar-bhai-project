"""FastAPI routes for public booking and the authenticated CRM dashboard."""

import re
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from .auth import create_access_token, current_user_dependency, verify_password
from .config import Settings
from .storage import BotStore

IST = ZoneInfo("Asia/Kolkata")
BUSINESS_START = time(9, 0)
BUSINESS_END = time(18, 30)
MEETING_STATUSES = {"requested", "confirmed", "scheduled", "completed", "cancelled", "no_show"}
LEAD_STAGES = {"new", "qualified", "proposal", "won", "lost"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class PublicMeetingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    email: str = Field(min_length=5, max_length=200)
    meeting_date: date
    start_time: time

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) < 10 or len(digits) > 15:
            raise ValueError("Enter a valid phone number with country code")
        if len(digits) == 10:
            digits = f"91{digits}"
        return digits

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class NotificationSettingsUpdate(BaseModel):
    reminder_enabled: bool
    reminder_minutes_before: int = Field(ge=15, le=1440)
    followup_enabled: bool
    followup_days: list[int] = Field(min_length=1, max_length=10)
    reminder_template: str = Field(min_length=20, max_length=1500)
    followup_template: str = Field(min_length=20, max_length=1500)

    @field_validator("followup_days")
    @classmethod
    def validate_followup_days(cls, values: list[int]) -> list[int]:
        cleaned = sorted(set(values))
        if any(value < 1 or value > 90 for value in cleaned):
            raise ValueError("Follow-up days must be between 1 and 90")
        return cleaned

    @field_validator("reminder_template", "followup_template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        try:
            value.format(
                name="Test User",
                date="Monday, 1 January 2027",
                time="10:00 AM",
                minutes=60,
                days=1,
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Invalid message placeholder: {exc}") from exc
        return value


class MeetingUpdate(BaseModel):
    status: str | None = None
    lead_stage: str | None = None
    assigned_to: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=3000)
    start_at: str | None = None
    end_at: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in MEETING_STATUSES:
            raise ValueError("Invalid meeting status")
        return value

    @field_validator("lead_stage")
    @classmethod
    def validate_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in LEAD_STAGES:
            raise ValueError("Invalid lead stage")
        return value


def _slot_bounds(day: date, start: time, duration: int) -> tuple[datetime, datetime]:
    begins = datetime.combine(day, start, tzinfo=IST)
    return begins, begins + timedelta(minutes=duration)


def _validate_business_slot(day: date, start: time, duration: int) -> tuple[datetime, datetime]:
    if day.weekday() == 6:
        raise HTTPException(status_code=422, detail="Meetings are unavailable on Sundays")
    begins, ends = _slot_bounds(day, start, duration)
    now = datetime.now(IST)
    if begins <= now:
        raise HTTPException(status_code=422, detail="Please choose a future time")
    if begins.time() < BUSINESS_START or ends.time() > BUSINESS_END:
        raise HTTPException(
            status_code=422,
            detail="Choose a time between 9:00 AM and 6:30 PM IST, Monday-Saturday",
        )
    return begins, ends


def build_router(settings: Settings, store: BotStore) -> APIRouter:
    router = APIRouter()
    get_current_user = current_user_dependency(settings, store)

    @router.post("/api/auth/login")
    def login(payload: LoginRequest) -> dict[str, Any]:
        user = store.get_user_by_username(payload.username)
        if user is None or not verify_password(payload.password, str(user["password_hash"])):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account disabled")
        token = create_access_token(int(user["id"]), str(user["role"]), settings)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": _safe_user(user),
        }

    @router.get("/api/auth/me")
    def me(user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        return _safe_user(user)

    @router.get("/api/public/config")
    def public_config() -> dict[str, Any]:
        return {
            "company": "Mechman Solutions",
            "address": "256/50, Makarpura GIDC, Vadodara, Gujarat - 390010",
            "timezone": "Asia/Kolkata",
            "business_hours": "Monday-Saturday, 9:00 AM-6:30 PM IST",
            "duration_minutes": settings.meeting_duration_minutes,
        }

    @router.get("/api/public/slots")
    def available_slots(day: Annotated[date, Query(alias="date")]) -> list[dict[str, str]]:
        if day.weekday() == 6 or day < datetime.now(IST).date():
            return []
        day_start = datetime.combine(day, BUSINESS_START, tzinfo=IST)
        day_end = datetime.combine(day, BUSINESS_END, tzinfo=IST)
        busy = store.busy_ranges(day_start.isoformat(), day_end.isoformat())
        now = datetime.now(IST)
        cursor = day_start
        slots: list[dict[str, str]] = []
        while cursor + timedelta(minutes=settings.meeting_duration_minutes) <= day_end:
            end = cursor + timedelta(minutes=settings.meeting_duration_minutes)
            occupied = any(
                cursor < datetime.fromisoformat(row["end_at"])
                and datetime.fromisoformat(row["start_at"]) < end
                for row in busy
            )
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
    def create_public_meeting(payload: PublicMeetingCreate) -> dict[str, Any]:
        begins, ends = _validate_business_slot(
            payload.meeting_date, payload.start_time, settings.meeting_duration_minutes
        )
        try:
            meeting_id = store.create_meeting(
                {
                    **payload.model_dump(exclude={"meeting_date", "start_time"}),
                    "company": "",
                    "interest": "General enquiry",
                    "purpose": "Meeting requested through the booking form",
                    "meeting_mode": "WhatsApp or phone call",
                    "start_at": begins.isoformat(),
                    "end_at": ends.isoformat(),
                    "preferred_date": payload.meeting_date.isoformat(),
                    "preferred_time": payload.start_time.strftime("%H:%M"),
                    "source": "web_form",
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "meeting_id": meeting_id,
            "status": "requested",
            "start_at": begins.isoformat(),
            "end_at": ends.isoformat(),
            "message": "Your meeting request is recorded. The Mechman team will confirm it shortly.",
        }

    @router.get("/api/dashboard/analytics")
    def analytics(_: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        return store.analytics()

    @router.get("/api/meetings")
    def meetings(
        _: Annotated[dict[str, Any], Depends(get_current_user)],
        q: str = "",
        meeting_status: Annotated[str, Query(alias="status")] = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, Any]]:
        return store.list_meetings(
            query=q, status=meeting_status, date_from=date_from, date_to=date_to
        )

    @router.get("/api/meetings/{meeting_id}")
    def meeting_detail(
        meeting_id: int, _: Annotated[dict[str, Any], Depends(get_current_user)]
    ) -> dict[str, Any]:
        meeting = store.get_meeting(meeting_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return meeting

    @router.patch("/api/meetings/{meeting_id}")
    def update_meeting(
        meeting_id: int,
        payload: MeetingUpdate,
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        updated = store.update_meeting(
            meeting_id,
            payload.model_dump(exclude_none=True),
            changed_by=str(user["username"]),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return updated

    @router.get("/api/crm/contacts")
    def contacts(
        _: Annotated[dict[str, Any], Depends(get_current_user)], q: str = ""
    ) -> list[dict[str, Any]]:
        return store.list_contacts(q)

    @router.get("/api/crm/contacts/{contact_id}")
    def contact_detail(
        contact_id: int, _: Annotated[dict[str, Any], Depends(get_current_user)]
    ) -> dict[str, Any]:
        contact = store.get_contact(contact_id)
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        return contact

    @router.get("/api/settings/notifications")
    def notification_settings(
        _: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        return store.get_notification_settings()

    @router.put("/api/settings/notifications")
    def save_notification_settings(
        payload: NotificationSettingsUpdate,
        _: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        return store.update_notification_settings(payload.model_dump())

    @router.get("/api/settings/notifications/deliveries")
    def notification_deliveries(
        _: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> list[dict[str, Any]]:
        return store.recent_notification_deliveries()

    @router.get("/healthz")
    def healthz() -> dict[str, Literal["ok"]]:
        return {"status": "ok"}

    return router


def _safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
    }
