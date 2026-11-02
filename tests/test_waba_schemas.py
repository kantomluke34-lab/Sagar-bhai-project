from fastapi import FastAPI
from pydantic import ValidationError

from mechman_bot.waba_schemas import (
    ConversationControlResponse,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
    ManualMessage,
    TemplateDraft,
    TemplateSyncResponse,
    WabaStatus,
    WabaWebhookPayload,
    WebhookAcknowledgement,
    WhatsAppTemplate,
)


def test_manual_message_requires_one_delivery_mode() -> None:
    assert ManualMessage(text="Hello").text == "Hello"
    assert ManualMessage(template_id=7, parameters=["Kunj"]).template_id == 7

    for invalid in ({}, {"text": "Hello", "template_id": 7}):
        try:
            ManualMessage.model_validate(invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError("ManualMessage accepted an ambiguous payload")


def test_template_draft_contract_matches_meta_limits() -> None:
    draft = TemplateDraft.model_validate(
        {
            "name": "meeting_confirmation",
            "category": "UTILITY",
            "body": "Hello {{1}}, your meeting is confirmed for {{2}}.",
            "variables": ["Customer name", "Tuesday 3:00 PM"],
            "buttons": [{"type": "QUICK_REPLY", "text": "Confirm"}],
        }
    )
    assert draft.language == "en_US"
    assert draft.buttons[0].text == "Confirm"

    try:
        TemplateDraft(name="Invalid name", body="Hello")
    except ValidationError:
        pass
    else:
        raise AssertionError("TemplateDraft accepted a name Meta will reject")


def test_webhook_contract_handles_inbound_messages_and_delivery_statuses() -> None:
    inbound = WabaWebhookPayload.model_validate(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "+91 99999 99999",
                                    "phone_number_id": "phone-1",
                                },
                                "contacts": [{"wa_id": "919876543210", "profile": {"name": "Raj"}}],
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "id": "wamid.1",
                                        "timestamp": "1793630000",
                                        "type": "text",
                                        "text": {"body": "I need a quotation"},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )
    message = inbound.entry[0].changes[0].value.messages[0]
    assert message.from_ == "919876543210"
    assert message.text is not None and message.text.body == "I need a quotation"

    delivered = WabaWebhookPayload.model_validate(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "phone-1"},
                                "statuses": [
                                    {
                                        "id": "wamid.1",
                                        "status": "delivered",
                                        "timestamp": "1793630010",
                                        "recipient_id": "919876543210",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )
    assert delivered.entry[0].changes[0].value.statuses[0].status == "delivered"


def test_v3_openapi_contracts_are_component_references_not_generic_objects() -> None:
    app = FastAPI()

    app.get("/api/conversations", response_model=list[ConversationSummary])(lambda: [])
    app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)(
        lambda conversation_id: None
    )
    app.post(
        "/api/conversations/{conversation_id}/take-over",
        response_model=ConversationControlResponse,
    )(lambda conversation_id: None)
    app.post("/api/conversations/{conversation_id}/messages", response_model=ConversationMessage)(
        lambda conversation_id, payload: None
    )
    app.get("/api/waba/status", response_model=WabaStatus)(lambda: None)
    app.get("/api/templates", response_model=list[WhatsAppTemplate])(lambda: [])
    app.post("/api/templates", response_model=WhatsAppTemplate)(lambda payload: None)
    app.post("/api/templates/sync", response_model=TemplateSyncResponse)(lambda: None)
    app.post("/webhook", response_model=WebhookAcknowledgement)(lambda payload: None)

    document = app.openapi()
    schemas = document["components"]["schemas"]
    for name in (
        "ConversationSummary",
        "ConversationDetail",
        "ConversationControlResponse",
        "ConversationMessage",
        "WabaStatus",
        "WhatsAppTemplate",
        "TemplateSyncResponse",
        "WebhookAcknowledgement",
    ):
        assert schemas[name]["type"] == "object"
        assert schemas[name].get("properties")
        assert schemas[name].get("additionalProperties") is not True

    list_schema = document["paths"]["/api/conversations"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert list_schema["items"]["$ref"] == "#/components/schemas/ConversationSummary"
