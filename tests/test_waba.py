import hashlib
import hmac
from unittest.mock import AsyncMock

import httpx
import pytest

from mechman_bot.config import Settings
from mechman_bot.waba import WABAClient, WABAError


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


def test_webhook_signature_fails_closed_without_app_secret() -> None:
    client = WABAClient(settings(meta_app_secret=""))
    assert not client.validate_signature(b"{}", None)
    assert not client.validate_signature(b"{}", "sha256=anything")


def test_http_429_is_always_classified_as_throttle() -> None:
    assert WABAError("rate limited", http_status=429).is_throttle


def test_web_service_rejects_disabled_dashboard_auth() -> None:
    with pytest.raises(ValueError, match="DASHBOARD_AUTH_ENABLED"):
        settings(dashboard_auth_enabled=False).validate_web()


@pytest.mark.asyncio
async def test_account_health_combines_business_limit_and_phone_quality() -> None:
    client = WABAClient(settings())
    client._get = AsyncMock(
        side_effect=[
            {"status": "ACTIVE", "whatsapp_business_manager_messaging_limit": "TIER_2K"},
            {
                "display_phone_number": "+91 99999 99999",
                "verified_name": "Mechman",
                "quality_rating": "GREEN",
                "name_status": "APPROVED",
                "status": "CONNECTED",
            },
        ]
    )

    result = await client.account_health()

    assert result["messaging_limit_tier"] == "TIER_2K"
    assert result["quality_rating"] == "GREEN"
    assert client._get.await_args_list[0].args[0] == client.settings.meta_waba_id


@pytest.mark.asyncio
async def test_meta_throttle_error_is_structured(monkeypatch) -> None:
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "mechman_bot.waba.httpx.AsyncClient",
        lambda **kwargs: async_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "error": {
                            "code": 130429,
                            "message": "Rate limit hit",
                            "error_data": {"details": "Too many messages in a short period"},
                        }
                    },
                )
            ),
            **kwargs,
        ),
    )
    client = WABAClient(settings())

    with pytest.raises(WABAError) as caught:
        await client._post("phone/messages", {})

    assert caught.value.is_throttle
    assert caught.value.code == 130429
    assert "Too many messages" in str(caught.value)


@pytest.mark.asyncio
async def test_all_sender_paths_honor_and_trip_shared_throttle(monkeypatch) -> None:
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "mechman_bot.waba.httpx.AsyncClient",
        lambda **kwargs: async_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429, json={"error": {"code": 131048, "message": "Sender throttled"}}
                )
            ),
            **kwargs,
        ),
    )
    client = WABAClient(settings())
    on_throttle = AsyncMock()
    is_throttled = AsyncMock(return_value=False)
    client.set_throttle_hooks(on_throttle, is_throttled)

    with pytest.raises(WABAError):
        await client.send_text("919876543210", "Hello")
    on_throttle.assert_awaited_once()

    is_throttled.return_value = True
    with pytest.raises(WABAError, match="cooldown"):
        await client.send_template("919876543210", "welcome", "en_US")


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

    await client.submit_template(
        {
            "name": "product_photo",
            "language": "en_US",
            "category": "MARKETING",
            "header_format": "IMAGE",
            "header_sample_handle": "4::sample-handle",
            "body": "See our product range.",
            "variables": [],
        }
    )

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


@pytest.mark.asyncio
async def test_template_send_maps_flow_choices_to_quick_reply_payloads() -> None:
    client = WABAClient(settings())
    client._post = AsyncMock(return_value={"messages": [{"id": "wamid.flow"}]})

    message_id = await client.send_template(
        "919876543210",
        "campaign_reply",
        "en_US",
        quick_reply_payloads=["dmf:yes", "dmf:no"],
    )

    components = client._post.await_args.args[1]["template"]["components"]
    assert message_id == "wamid.flow"
    assert components == [
        {
            "type": "button",
            "sub_type": "quick_reply",
            "index": "0",
            "parameters": [{"type": "payload", "payload": "dmf:yes"}],
        },
        {
            "type": "button",
            "sub_type": "quick_reply",
            "index": "1",
            "parameters": [{"type": "payload", "payload": "dmf:no"}],
        },
    ]
