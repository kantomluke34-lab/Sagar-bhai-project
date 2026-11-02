import pytest

from mechman_bot.webhook import WebhookProcessor


class FakeSettings:
    public_booking_url = "https://example.com/book"


class FakeRepository:
    def __init__(self, taken_over: bool = False) -> None:
        self.taken_over = taken_over
        self.messages = []
        self.state = None

    async def update_message_status(self, message_id, status, error=None):
        self.messages.append(("status", message_id, status, error))

    async def upsert_conversation(self, phone, display_name):
        return {"id": 1, "phone": phone, "bot_state": {}, "is_taken_over": self.taken_over}

    async def add_message(self, conversation_id, **values):
        if any(
            item[0] == "inbound" and item[1].get("wa_message_id") == values.get("wa_message_id")
            for item in self.messages
            if isinstance(item, tuple)
        ):
            return None
        self.messages.append((values["direction"], values))
        return values

    async def save_bot_state(self, conversation_id, state):
        self.state = state


class FakeWABA:
    def __init__(self) -> None:
        self.sent = []

    async def send_text(self, phone, message):
        self.sent.append((phone, message))
        return f"wamid.{len(self.sent)}"


def payload(message_id="wamid.in.1"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "919999999999", "profile": {"name": "Dev"}}],
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": "919999999999",
                                    "timestamp": "1793491200",
                                    "type": "text",
                                    "text": {"body": "hi"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_inbound_message_is_logged_and_bot_replies() -> None:
    repository = FakeRepository()
    waba = FakeWABA()
    processor = WebhookProcessor(FakeSettings(), repository, waba)
    await processor.process(payload())
    assert repository.state["stage"] == "welcome"
    assert waba.sent and waba.sent[0][0] == "919999999999"
    assert any(item[0] == "outbound" for item in repository.messages)


@pytest.mark.asyncio
async def test_takeover_logs_inbound_without_bot_reply() -> None:
    repository = FakeRepository(taken_over=True)
    waba = FakeWABA()
    processor = WebhookProcessor(FakeSettings(), repository, waba)
    await processor.process(payload())
    assert not waba.sent
    assert repository.state is None


@pytest.mark.asyncio
async def test_delivery_failure_preserves_meta_error_detail() -> None:
    repository = FakeRepository()
    processor = WebhookProcessor(FakeSettings(), repository, FakeWABA())
    await processor.process(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.failed",
                                        "status": "failed",
                                        "errors": [
                                            {
                                                "title": "Delivery failed",
                                                "error_data": {"details": "Recipient is not valid"},
                                            }
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert repository.messages == [
        ("status", "wamid.failed", "failed", "Recipient is not valid")
    ]
