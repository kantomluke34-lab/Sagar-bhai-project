import hashlib
import hmac
from unittest.mock import AsyncMock

import httpx
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


@pytest.mark.asyncio
async def test_media_template_submission_uses_review_sample_handle() -> None:
    client = WABAClient(settings())
    client._post = AsyncMock(return_value={"id": "template-2"})

    await client.submit_template({
        "name": "product_photo",
        "language": "en_US",
        "category": "MARKETING",
        "header_format": "IMAGE",
        "header_sample_handle": "4::sample-handle",
        "body": "See our product range.",
        "variables": [],
    })

    components = client._post.await_args.args[1]["components"]
    assert components[0] == {
        "type": "HEADER",
        "format": "IMAGE",
        "example": {"header_handle": ["4::sample-handle"]},
    }


@pytest.mark.asyncio
async def test_media_review_sample_upload_uses_app_id_and_file_name(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/uploads"):
            return httpx.Response(200, json={"id": "upload:sample-session"})
        return httpx.Response(200, json={"h": "4::sample-handle"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "mechman_bot.waba.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    client = WABAClient(settings(meta_app_id="2545072705904292"))

    handle = await client.upload_template_header_sample(b"sample", "image/png", "product.png")

    assert handle == "4::sample-handle"
    assert requests[0].url.path.endswith("/2545072705904292/uploads")
    assert requests[0].url.params["file_name"] == "product.png"
    assert requests[0].url.params["file_length"] == "6"
    assert requests[1].headers["file_offset"] == "0"
    assert requests[1].content == b"sample"


@pytest.mark.asyncio
async def test_media_template_send_includes_header_and_body_parameters() -> None:
    client = WABAClient(settings())
    client._post = AsyncMock(return_value={"messages": [{"id": "wamid.123"}]})

    message_id = await client.send_template(
        "919876543210",
        "product_brochure",
        "en_US",
        ["Asha", "PowerMill"],
        header_type="DOCUMENT",
        header_media_id="media-1",
        header_filename="brochure.pdf",
    )

    payload = client._post.await_args.args[1]
    components = payload["template"]["components"]
    assert message_id == "wamid.123"
    assert components[0]["parameters"][0]["document"] == {
        "id": "media-1",
        "filename": "brochure.pdf",
    }
    assert [item["text"] for item in components[1]["parameters"]] == ["Asha", "PowerMill"]
