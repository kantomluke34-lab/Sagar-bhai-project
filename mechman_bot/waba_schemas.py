"""Typed API contracts for the Meta WhatsApp Cloud API dashboard.

The current repository does not contain the v3 persistence or Meta transport
services, so these models deliberately contain no route or network behaviour.
They can be imported by the v3 handlers as request/response models without
coupling those handlers to a database implementation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class ApiModel(BaseModel):
    """Common compatibility settings for records returned by Meta and storage."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ConversationMode(StrEnum):
    BOT = "bot"
    HUMAN = "human"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ConversationMessage(ApiModel):
    id: int
    conversation_id: int | None = None
    whatsapp_message_id: str | None = None
    direction: MessageDirection
    type: str = "text"
    text: str | None = None
    status: str | None = None
    sent_at: datetime | None = None
    created_at: datetime | None = None


class ConversationSummary(ApiModel):
    id: int
    phone: str
    wa_id: str | None = None
    contact_name: str | None = None
    profile_name: str | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    control_mode: ConversationMode = ConversationMode.BOT
    human_takeover: bool = False
    unread_count: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationControlResponse(ApiModel):
    id: int
    control_mode: ConversationMode
    human_takeover: bool
    updated_at: datetime | None = None


class ManualMessage(ApiModel):
    text: str | None = Field(default=None, min_length=1, max_length=4096)
    template_id: int | None = Field(default=None, ge=1)
    parameters: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_content(self) -> ManualMessage:
        if (self.text is None) == (self.template_id is None):
            raise ValueError("Provide exactly one of text or template_id")
        return self


class WabaStatus(ApiModel):
    status: str
    connected: bool
    connection_status: str | None = None
    verified_name: str | None = None
    display_phone_number: str | None = None
    phone_number_id: str | None = None
    waba_id: str | None = None
    quality_rating: str | None = None
    app_secret_configured: bool = False
    verify_token_configured: bool = False
    webhook_signature_configured: bool = False
    webhook_verify_token_configured: bool = False
    last_checked_at: datetime | None = None
    error: str | None = None


class TemplateCategory(StrEnum):
    UTILITY = "UTILITY"
    MARKETING = "MARKETING"
    AUTHENTICATION = "AUTHENTICATION"


class TemplateButton(ApiModel):
    type: str
    text: str
    url: str | None = None
    phone_number: str | None = None
    example: list[str] = Field(default_factory=list)


class TemplateDraft(ApiModel):
    name: str = Field(min_length=3, max_length=512, pattern=r"^[a-z0-9_]+$")
    language: str = Field(default="en_US", min_length=2, max_length=20)
    category: TemplateCategory = TemplateCategory.UTILITY
    header: str | None = Field(default=None, max_length=60)
    body: str = Field(min_length=1, max_length=1024)
    footer: str | None = Field(default=None, max_length=60)
    buttons: list[TemplateButton] = Field(default_factory=list, max_length=10)
    variables: list[str] = Field(default_factory=list, max_length=20)


class WhatsAppTemplate(TemplateDraft):
    id: int
    meta_template_id: str | None = None
    status: str = "draft"
    approval_status: str | None = None
    rejected_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TemplateSyncResponse(ApiModel):
    created: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    unchanged: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)


class WebhookVerification(ApiModel):
    mode: str = Field(default="", alias="hub.mode")
    verify_token: str = Field(default="", alias="hub.verify_token")
    challenge: str = Field(default="", alias="hub.challenge")


class WebhookChallenge(RootModel[str]):
    """The webhook verification response is the raw challenge string."""


class WabaProfile(ApiModel):
    name: str | None = None


class WabaContact(ApiModel):
    wa_id: str
    profile: WabaProfile | None = None


class WabaMetadata(ApiModel):
    display_phone_number: str | None = None
    phone_number_id: str


class WabaText(ApiModel):
    body: str


class WabaMedia(ApiModel):
    id: str
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None
    filename: str | None = None


class WabaLocation(ApiModel):
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


class WabaButton(ApiModel):
    text: str | None = None
    payload: str | None = None


class WabaReply(ApiModel):
    id: str
    title: str
    description: str | None = None


class WabaInteractive(ApiModel):
    type: str
    button_reply: WabaReply | None = None
    list_reply: WabaReply | None = None


class WabaMessageContext(ApiModel):
    from_: str | None = Field(default=None, alias="from")
    id: str | None = None


class WabaMessage(ApiModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    type: str
    context: WabaMessageContext | None = None
    text: WabaText | None = None
    image: WabaMedia | None = None
    audio: WabaMedia | None = None
    document: WabaMedia | None = None
    video: WabaMedia | None = None
    location: WabaLocation | None = None
    button: WabaButton | None = None
    interactive: WabaInteractive | None = None


class WabaErrorData(ApiModel):
    messaging_product: str | None = None
    details: str | None = None


class WabaError(ApiModel):
    code: int
    title: str | None = None
    message: str | None = None
    error_data: WabaErrorData | None = None


class WabaStatusConversation(ApiModel):
    id: str
    expiration_timestamp: str | None = None
    origin_type: str | None = None


class WabaPricing(ApiModel):
    billable: bool | None = None
    pricing_model: str | None = None
    category: str | None = None


class WabaDeliveryStatus(ApiModel):
    id: str
    status: str
    timestamp: str
    recipient_id: str
    conversation: WabaStatusConversation | None = None
    pricing: WabaPricing | None = None
    errors: list[WabaError] = Field(default_factory=list)


class WabaWebhookValue(ApiModel):
    messaging_product: Literal["whatsapp"] | str = "whatsapp"
    metadata: WabaMetadata
    contacts: list[WabaContact] = Field(default_factory=list)
    messages: list[WabaMessage] = Field(default_factory=list)
    statuses: list[WabaDeliveryStatus] = Field(default_factory=list)
    errors: list[WabaError] = Field(default_factory=list)


class WabaWebhookChange(ApiModel):
    field: str
    value: WabaWebhookValue


class WabaWebhookEntry(ApiModel):
    id: str
    changes: list[WabaWebhookChange]


class WabaWebhookPayload(ApiModel):
    object: Literal["whatsapp_business_account"]
    entry: list[WabaWebhookEntry]


class WebhookAcknowledgement(ApiModel):
    status: Literal["ok"] = "ok"


__all__ = [
    "ConversationControlResponse",
    "ConversationDetail",
    "ConversationMessage",
    "ConversationSummary",
    "ManualMessage",
    "TemplateDraft",
    "TemplateSyncResponse",
    "WabaStatus",
    "WabaWebhookPayload",
    "WebhookAcknowledgement",
    "WebhookChallenge",
    "WebhookVerification",
    "WhatsAppTemplate",
]
