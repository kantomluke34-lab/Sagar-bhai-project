"""Database operations used by the API, WABA webhook, and scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from .database import (
    AppSetting,
    Contact,
    Conversation,
    Database,
    Meeting,
    MeetingHistory,
    Message,
    MessageTemplate,
    NotificationDelivery,
    User,
    as_dict,
)

DEFAULT_NOTIFICATION_SETTINGS = {
    "reminder_enabled": True,
    "reminder_minutes_before": 60,
    "followup_enabled": True,
    "followup_days": [1, 3],
    "reminder_template": (
        "Hi {name}, a quick reminder from Mechman Solutions — your meeting is "
        "scheduled for {date} at {time} IST. See you in about {minutes} minutes."
    ),
    "followup_template": (
        "Hi {name}, following up {days} day(s) after our Mechman Solutions meeting "
        "on {date}. Is there anything you would like us to clarify?"
    ),
}


class CRMRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def seed(self, username: str, password_hash: str) -> None:
        async with self.database.session_factory() as session:
            user = await session.scalar(
                select(User).where(func.lower(User.username) == username.lower())
            )
            if user is None:
                session.add(
                    User(username=username, full_name="Mechman Admin", password_hash=password_hash)
                )
            setting = await session.get(AppSetting, "notifications")
            if setting is None:
                session.add(AppSetting(key="notifications", value=DEFAULT_NOTIFICATION_SETTINGS))
            await session.commit()

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            row = await session.scalar(
                select(User).where(func.lower(User.username) == username.lower())
            )
            return as_dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            row = await session.get(User, user_id)
            return as_dict(row) if row else None

    async def upsert_conversation(
        self, phone: str, display_name: str = "", source: str = "whatsapp"
    ) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            contact = await session.scalar(select(Contact).where(Contact.phone == phone))
            if contact is None:
                contact = Contact(
                    name=display_name or "WhatsApp contact", phone=phone, source=source
                )
                session.add(contact)
                await session.flush()
            elif display_name and contact.name in {"", "WhatsApp contact"}:
                contact.name = display_name
            conversation = await session.scalar(
                select(Conversation).where(Conversation.phone == phone)
            )
            if conversation is None:
                conversation = Conversation(
                    contact_id=contact.id,
                    phone=phone,
                    display_name=display_name or contact.name,
                    bot_state={"stage": "welcome"},
                )
                session.add(conversation)
                await session.flush()
            elif display_name:
                conversation.display_name = display_name
            await session.commit()
            await session.refresh(conversation)
            result = as_dict(conversation)
            result["contact_name"] = contact.name
            return result

    async def get_conversation(self, conversation_id: int) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            conversation = await session.scalar(
                select(Conversation)
                .options(selectinload(Conversation.contact))
                .where(Conversation.id == conversation_id)
            )
            if not conversation:
                return None
            result = as_dict(conversation)
            result["contact_name"] = conversation.contact.name
            result["contact"] = as_dict(conversation.contact)
            return result

    async def get_conversation_by_phone(self, phone: str) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(Conversation.phone == phone)
            )
            return as_dict(conversation) if conversation else None

    async def save_bot_state(self, conversation_id: int, state: dict[str, Any]) -> None:
        async with self.database.session_factory() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                conversation.bot_state = state
                conversation.language = str(state.get("language", conversation.language))
                await session.commit()

    async def list_conversations(self, query: str = "") -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            statement = (
                select(Conversation)
                .options(selectinload(Conversation.contact))
                .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
            )
            if query:
                pattern = f"%{query}%"
                statement = statement.join(Contact).where(
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.phone.ilike(pattern),
                        Contact.company.ilike(pattern),
                    )
                )
            rows = (await session.scalars(statement)).all()
            results = []
            for row in rows:
                item = as_dict(row)
                item["contact_name"] = row.contact.name
                last = await session.scalar(
                    select(Message)
                    .where(Message.conversation_id == row.id)
                    .order_by(Message.occurred_at.desc())
                    .limit(1)
                )
                item["last_message"] = last.body if last else ""
                results.append(item)
            return results

    async def set_takeover(self, conversation_id: int, taken_over: bool) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                return None
            conversation.is_taken_over = taken_over
            conversation.taken_over_at = datetime.now(UTC) if taken_over else None
            await session.commit()
            await session.refresh(conversation)
            return as_dict(conversation)

    async def add_message(
        self,
        conversation_id: int,
        *,
        direction: str,
        body: str,
        sender: str,
        wa_message_id: str | None = None,
        message_type: str = "text",
        status: str = "received",
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            message = Message(
                conversation_id=conversation_id,
                direction=direction,
                body=body,
                sender=sender,
                wa_message_id=wa_message_id or None,
                message_type=message_type,
                status=status,
                metadata_json=metadata or {},
                occurred_at=occurred_at or datetime.now(UTC),
            )
            session.add(message)
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                conversation.last_message_at = message.occurred_at
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
            await session.refresh(message)
            return as_dict(message)

    async def list_messages(self, conversation_id: int, limit: int = 200) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.occurred_at.desc())
                    .limit(limit)
                )
            ).all()
            return [as_dict(row) for row in reversed(rows)]

    async def within_service_window(self, conversation_id: int) -> bool:
        async with self.database.session_factory() as session:
            last_inbound = await session.scalar(
                select(func.max(Message.occurred_at)).where(
                    Message.conversation_id == conversation_id,
                    Message.direction == "inbound",
                )
            )
            return bool(last_inbound and last_inbound >= datetime.now(UTC) - timedelta(hours=24))

    async def update_message_status(self, wa_message_id: str, status: str) -> None:
        async with self.database.session_factory() as session:
            row = await session.scalar(
                select(Message).where(Message.wa_message_id == wa_message_id)
            )
            if row:
                row.status = status
                await session.commit()

    async def create_meeting(self, data: dict[str, Any]) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            contact = await session.scalar(select(Contact).where(Contact.phone == data["phone"]))
            if contact is None:
                contact = Contact(
                    name=data["name"],
                    phone=data["phone"],
                    email=data.get("email"),
                    source=data.get("source", "web_form"),
                )
                session.add(contact)
                await session.flush()
            else:
                contact.name = data["name"] or contact.name
                contact.email = data.get("email") or contact.email
            conversation = await session.scalar(
                select(Conversation).where(Conversation.phone == data["phone"])
            )
            meeting = Meeting(
                contact_id=contact.id,
                conversation_id=conversation.id if conversation else None,
                **{
                    key: value
                    for key, value in data.items()
                    if key not in {"contact_id", "conversation_id"}
                },
            )
            session.add(meeting)
            await session.flush()
            session.add(
                MeetingHistory(
                    meeting_id=meeting.id,
                    action="meeting_created",
                    new_value=meeting.status,
                    changed_by="booking_form",
                )
            )
            await session.commit()
            await session.refresh(meeting)
            return as_dict(meeting)

    async def busy_ranges(self, begins: datetime, ends: datetime) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(Meeting).where(
                        Meeting.status.not_in(["cancelled", "no_show"]),
                        Meeting.start_at < ends,
                        Meeting.end_at > begins,
                    )
                )
            ).all()
            return [as_dict(row) for row in rows]

    async def list_meetings(
        self, query: str = "", status: str = "", date_from: str = "", date_to: str = ""
    ) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            statement = select(Meeting).order_by(Meeting.start_at.desc())
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(
                        Meeting.name.ilike(pattern),
                        Meeting.phone.ilike(pattern),
                        Meeting.company.ilike(pattern),
                        Meeting.purpose.ilike(pattern),
                    )
                )
            if status:
                statement = statement.where(Meeting.status == status)
            if date_from:
                statement = statement.where(Meeting.start_at >= datetime.fromisoformat(date_from))
            if date_to:
                statement = statement.where(
                    Meeting.start_at < datetime.fromisoformat(date_to) + timedelta(days=1)
                )
            rows = (await session.scalars(statement)).all()
            return [as_dict(row) for row in rows]

    async def get_meeting(self, meeting_id: int) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            meeting = await session.get(Meeting, meeting_id)
            if not meeting:
                return None
            result = as_dict(meeting)
            history = (
                await session.scalars(
                    select(MeetingHistory)
                    .where(MeetingHistory.meeting_id == meeting_id)
                    .order_by(MeetingHistory.created_at.desc())
                )
            ).all()
            result["history"] = [as_dict(row) for row in history]
            return result

    async def update_meeting(
        self, meeting_id: int, values: dict[str, Any], changed_by: str
    ) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            meeting = await session.get(Meeting, meeting_id)
            if not meeting:
                return None
            for key, value in values.items():
                if not hasattr(meeting, key):
                    continue
                old = getattr(meeting, key)
                if old != value:
                    setattr(meeting, key, value)
                    session.add(
                        MeetingHistory(
                            meeting_id=meeting.id,
                            action=f"{key}_changed",
                            old_value=str(old) if old is not None else None,
                            new_value=str(value) if value is not None else None,
                            changed_by=changed_by,
                        )
                    )
            await session.commit()
            await session.refresh(meeting)
            return as_dict(meeting)

    async def list_contacts(self, query: str = "") -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            statement = select(Contact).order_by(Contact.updated_at.desc())
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.phone.ilike(pattern),
                        Contact.company.ilike(pattern),
                    )
                )
            contacts = (await session.scalars(statement)).all()
            results = []
            for contact in contacts:
                item = as_dict(contact)
                meetings = (
                    await session.scalars(select(Meeting).where(Meeting.contact_id == contact.id))
                ).all()
                item["meeting_count"] = len(meetings)
                upcoming = [
                    m.start_at
                    for m in meetings
                    if m.start_at >= datetime.now(UTC) and m.status not in {"cancelled", "no_show"}
                ]
                item["next_meeting"] = min(upcoming) if upcoming else None
                item["last_activity"] = max(
                    (m.updated_at for m in meetings), default=contact.updated_at
                )
                results.append(item)
            return results

    async def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            contact = await session.get(Contact, contact_id)
            if not contact:
                return None
            result = as_dict(contact)
            meetings = (
                await session.scalars(
                    select(Meeting)
                    .where(Meeting.contact_id == contact_id)
                    .order_by(Meeting.start_at.desc())
                )
            ).all()
            result["meetings"] = [as_dict(row) for row in meetings]
            return result

    async def analytics(self) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            now = datetime.now(UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            total = await session.scalar(select(func.count(Meeting.id))) or 0
            upcoming = (
                await session.scalar(
                    select(func.count(Meeting.id)).where(
                        Meeting.start_at >= datetime.now(UTC),
                        Meeting.status.not_in(["cancelled", "no_show"]),
                    )
                )
                or 0
            )
            contacts = await session.scalar(select(func.count(Contact.id))) or 0
            today = (
                await session.scalar(
                    select(func.count(Meeting.id)).where(
                        Meeting.start_at >= today_start,
                        Meeting.start_at < today_end,
                        Meeting.status.not_in(["cancelled", "no_show"]),
                    )
                )
                or 0
            )
            by_status_rows = (
                await session.execute(
                    select(Meeting.status, func.count(Meeting.id)).group_by(Meeting.status)
                )
            ).all()
            by_stage_rows = (
                await session.execute(
                    select(Meeting.lead_stage, func.count(Meeting.id)).group_by(Meeting.lead_stage)
                )
            ).all()
            by_source_rows = (
                await session.execute(
                    select(Meeting.source, func.count(Meeting.id)).group_by(Meeting.source)
                )
            ).all()
            recent = (
                await session.scalars(select(Meeting).order_by(Meeting.created_at.desc()).limit(8))
            ).all()
            trend_rows = (
                await session.execute(
                    select(
                        func.to_char(Meeting.created_at, "YYYY-MM").label("month"),
                        func.count(Meeting.id),
                    )
                    .where(Meeting.created_at >= now - timedelta(days=365))
                    .group_by("month")
                    .order_by("month")
                )
            ).all()
            return {
                "total_meetings": total,
                "upcoming_meetings": upcoming,
                "total_contacts": contacts,
                "today_meetings": today,
                "new_requests": sum(
                    count for status, count in by_status_rows if status == "requested"
                ),
                "by_status": [{"status": key, "count": count} for key, count in by_status_rows],
                "by_stage": [{"stage": key, "count": count} for key, count in by_stage_rows],
                "by_source": [{"source": key, "count": count} for key, count in by_source_rows],
                "recent_meetings": [as_dict(row) for row in recent],
                "monthly_trend": [{"month": month, "count": count} for month, count in trend_rows],
            }

    async def notification_settings(self) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            row = await session.get(AppSetting, "notifications")
            return dict(row.value) if row else dict(DEFAULT_NOTIFICATION_SETTINGS)

    async def save_notification_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            row = await session.get(AppSetting, "notifications")
            if row is None:
                row = AppSetting(key="notifications", value=values)
                session.add(row)
            else:
                row.value = values
            await session.commit()
            return dict(values)

    async def list_deliveries(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            rows = (
                await session.execute(
                    select(NotificationDelivery, Meeting)
                    .join(Meeting, Meeting.id == NotificationDelivery.meeting_id)
                    .order_by(NotificationDelivery.sent_at.desc())
                    .limit(limit)
                )
            ).all()
            results = []
            for delivery, meeting in rows:
                item = as_dict(delivery)
                item["name"] = meeting.name
                item["start_at"] = meeting.start_at
                results.append(item)
            return results

    async def delivery_exists(self, meeting_id: int, key: str) -> bool:
        async with self.database.session_factory() as session:
            count = await session.scalar(
                select(func.count(NotificationDelivery.id)).where(
                    NotificationDelivery.meeting_id == meeting_id,
                    NotificationDelivery.notification_key == key,
                )
            )
            return bool(count)

    async def add_delivery(self, **values: Any) -> None:
        async with self.database.session_factory() as session:
            session.add(NotificationDelivery(**values))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def notification_candidates(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(Meeting).where(
                        Meeting.status.in_(["requested", "confirmed", "scheduled", "completed"]),
                        Meeting.start_at >= start,
                        Meeting.start_at <= end,
                    )
                )
            ).all()
            return [as_dict(row) for row in rows]

    async def create_template(self, values: dict[str, Any]) -> dict[str, Any]:
        async with self.database.session_factory() as session:
            row = MessageTemplate(**values)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return as_dict(row)

    async def list_templates(self) -> list[dict[str, Any]]:
        async with self.database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MessageTemplate).order_by(MessageTemplate.updated_at.desc())
                )
            ).all()
            return [as_dict(row) for row in rows]

    async def get_template(self, template_id: int) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            row = await session.get(MessageTemplate, template_id)
            return as_dict(row) if row else None

    async def update_template(
        self, template_id: int, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with self.database.session_factory() as session:
            row = await session.get(MessageTemplate, template_id)
            if not row:
                return None
            for key, value in values.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return as_dict(row)

    async def update_template_from_meta(
        self, name: str, language: str, values: dict[str, Any]
    ) -> None:
        async with self.database.session_factory() as session:
            row = await session.scalar(
                select(MessageTemplate).where(
                    MessageTemplate.name == name, MessageTemplate.language == language
                )
            )
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                row = MessageTemplate(
                    name=name,
                    language=language,
                    category=str(values.pop("category", "UTILITY")),
                    status=str(values.pop("status", "PENDING")),
                    body=str(values.pop("body", "Imported from Meta")),
                    **values,
                )
                session.add(row)
            await session.commit()
