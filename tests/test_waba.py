import hashlib
import hmac
from unittest.mock import AsyncMock

import pytest

from mechman_bot.config import Settings
from mechman_bot.waba import WABAClient


def settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "public_booking_url": "https://example.com/book",
        "frontend_origin": "https://example.com",
        "jwt_secret": "x" * 32,
        "jwt_expire_minutes": 720,
        "admin_username": "admin",
        "admin_password": "strong-password",
        "meeting_duration_minutes": 60,
        "log_level": "INFO",
        "meta_access_token": "token",
        "meta_phone_number_id": "1395187090344267",
        "meta_waba_id": "29459993996925480",
        "meta_api_version": "v26.0",
        "meta_webhook_verify_token": "verify",
        "meta_app_secret": "secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_webhook_signature_validation() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    client = WABAClient(settings())
    assert client.validate_signature(body, f"sha256={signature}")
    assert not client.validate_signature(body, "sha256=invalid")


def test_handoff_asset_configuration_is_supported() -> None:
    client = WABAClient(settings())
    assert client.base_url.endswith("/v26.0")
    assert client.settings.meta_waba_id == "29459993996925480"
    assert client.settings.meta_phone_number_id == "1395187090344267"


@pytest.mark.asyncio
async def test_template_submission_includes_variable_examples() -> None:
    client = WABAClient(settings())
    client._post = AsyncMock(return_value={"id": "template-1"})

    await client.submit_template(
        {
            "name": "meeting_reminder",
            "language": "en_US",
            "category": "UTILITY",
            "header": "Meeting reminder",
            "body": "Hi {{1}}, your meeting is at {{2}}.",
            "footer": "Mechman Solutions",
            "buttons": [],
            "variables": ["Kunj", "10:30 AM"],
        }
    )

    payload = client._post.await_args.args[1]
    body = next(item for item in payload["components"] if item["type"] == "BODY")
    assert body["example"] == {"body_text": [["Kunj", "10:30 AM"]]}
