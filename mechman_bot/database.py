"""Async PostgreSQL schema and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import Settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="Mechman Admin")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="WhatsApp contact")
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(120))
    lead_stage: Mapped[str] = mapped_column(String(30), default="new", index=True)
    source: Mapped[str] = mapped_column(String(40), default="whatsapp")
    assigned_to: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), unique=True
    )
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(8), default="en")
    bot_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_taken_over: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    taken_over_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    contact: Mapped[Contact] = relationship()
    messages: Mapped[list[Message]] = relationship(back_populates="conversation")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    wa_message_id: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)
    direction: Mapped[str] = mapped_column(String(12), index=True)
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    sender: Mapped[str] = mapped_column(String(30), default="customer")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), index=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(200), default="")
    interest: Mapped[str] = mapped_column(String(255), default="General enquiry")
    purpose: Mapped[str] = mapped_column(Text)
    meeting_mode: Mapped[str] = mapped_column(String(100), default="WhatsApp or phone call")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="requested", index=True)
    lead_stage: Mapped[str] = mapped_column(String(30), default="new", index=True)
    source: Mapped[str] = mapped_column(String(40), default="web_form")
    assigned_to: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[Contact] = relationship()


class MeetingHistory(Base):
    __tablename__ = "meeting_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageTemplate(Base, TimestampMixin):
    __tablename__ = "message_templates"
    __table_args__ = (UniqueConstraint("name", "language", name="uq_template_name_language"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    language: Mapped[str] = mapped_column(String(20), default="en_US")
    category: Mapped[str] = mapped_column(String(30), default="UTILITY")
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    meta_template_id: Mapped[str | None] = mapped_column(String(100))
    header: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    footer: Mapped[str | None] = mapped_column(Text)
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    variables: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("meeting_id", "notification_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    notification_key: Mapped[str] = mapped_column(String(100))
    recipient: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="sent")
    wa_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Database:
    def __init__(self, settings: Settings) -> None:
        url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session


def as_dict(model: Any) -> dict[str, Any]:
    return {column.key: getattr(model, column.key) for column in model.__table__.columns}
