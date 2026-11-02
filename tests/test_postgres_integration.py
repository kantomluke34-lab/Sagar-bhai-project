import hashlib
import hmac
import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from mechman_bot.config import Settings
from mechman_bot.web import create_app

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_postgres_auth_booking_and_calendar_api() -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        public_booking_url="https://crm.example.com/book",
        frontend_origin="https://crm.example.com",
        jwt_secret="integration-secret-that-is-at-least-32-chars",
        jwt_expire_minutes=720,
        admin_username="admin",
        admin_password="integration-password",
        meeting_duration_minutes=60,
        log_level="INFO",
        meta_access_token="",
        meta_phone_number_id="1395187090344267",
        meta_waba_id="29459993996925480",
        meta_api_version="v26.0",
        meta_webhook_verify_token="verify-token",
        meta_app_secret="app-secret",
            campaign_poll_seconds=5,
    )
    with TestClient(create_app(settings)) as client:
        ready = client.get("/readyz", headers={"X-Request-ID": "integration-ready"})
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready", "database": "ok"}
        assert ready.headers["X-Request-ID"] == "integration-ready"

        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "integration-password"}
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        wrong_password = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "wrong-password",
                "new_password": "replacement-password",
                "confirm_password": "replacement-password",
            },
        )
        assert wrong_password.status_code == 400

        changed = client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "integration-password",
                "new_password": "replacement-password",
                "confirm_password": "replacement-password",
            },
        )
        assert changed.status_code == 200
        relogin = client.post(
            "/api/auth/login", json={"username": "admin", "password": "replacement-password"}
        )
        assert relogin.status_code == 200

        meeting_day = date.today() + timedelta(days=2)
        while meeting_day.weekday() == 6:
            meeting_day += timedelta(days=1)
        booking = client.post(
            "/api/public/meetings",
            json={
                "name": "Integration Contact",
                "phone": "919999999991",
                "email": "integration@example.com",
                "meeting_date": meeting_day.isoformat(),
                "start_time": "09:00",
                "interest": "PowerMill",
                "purpose": "5-axis demo",
            },
        )
        assert booking.status_code == 201, booking.text

        meetings = client.get("/api/meetings", headers=headers)
        assert meetings.status_code == 200, meetings.text
        assert any(row["name"] == "Integration Contact" for row in meetings.json())

        contacts = client.get("/api/crm/contacts", headers=headers)
        assert contacts.status_code == 200
        assert any(row["phone"] == "919999999991" for row in contacts.json())
        contact = next(row for row in contacts.json() if row["phone"] == "919999999991")
        consent = client.put(
            f"/api/crm/contact-consent/{contact['id']}",
            headers=headers,
            json={
                "status": "opted_in",
                "source": "integration booking form",
                "captured_at": "2027-01-01T10:00:00+05:30",
            },
        )
        assert consent.status_code == 200, consent.text
        assert consent.json()["consent_status"] == "opted_in"

        audience = client.post(
            "/api/audiences",
            headers=headers,
            json={
                "name": "Integration web leads",
                "list_type": "dynamic",
                "filters": {"source": "web_form"},
                "member_ids": [],
            },
        )
        assert audience.status_code == 201, audience.text
        assert audience.json()["recipient_count"] == 1

        client.app.state.waba.list_meta_templates = AsyncMock(
            return_value=[
                {
                    "id": "meta-template-1",
                    "name": "integration_campaign",
                    "status": "APPROVED",
                    "language": "en_US",
                    "category": "MARKETING",
                    "components": [
                        {
                            "type": "BODY",
                            "text": "Hello {{1}}, this is an integration campaign.",
                            "example": {"body_text": [["Asha"]]},
                        }
                    ],
                }
            ]
        )
        synced = client.post("/api/templates/sync", headers=headers)
        assert synced.status_code == 200, synced.text
        template = next(
            row
            for row in client.get("/api/templates", headers=headers).json()
            if row["name"] == "integration_campaign"
        )
        client.app.state.waba.send_template = AsyncMock(return_value="wamid.campaign.integration")
        campaign = client.post(
            "/api/campaigns",
            headers=headers,
            json={
                "name": "Integration WABA campaign",
                "template_id": template["id"],
                "source_type": "paste",
                "recipients": [
                    {
                        "phone": "919777777777",
                        "name": "Asha",
                        "variables": {"name": "Asha", "phone": "919777777777"},
                    }
                ],
                "consent_confirmed": True,
                "consent_source": "integration opt-in",
                "consent_captured_at": datetime.now(UTC).isoformat(),
                "schedule_type": "once",
                "scheduled_at": datetime.now(UTC).isoformat(),
                "parameter_mapping": ["name"],
                "throttle_seconds": 0,
            },
        )
        assert campaign.status_code == 201, campaign.text
        campaign_id = campaign.json()["id"]
        campaign_detail = None
        for _ in range(15):
            campaign_detail = client.get(
                f"/api/campaigns/{campaign_id}", headers=headers
            ).json()
            if campaign_detail["status"] == "completed":
                break
            time.sleep(0.5)
        assert campaign_detail is not None
        assert campaign_detail["status"] == "completed"
        assert campaign_detail["sent_count"] == 1
        assert campaign_detail["deliveries"][0]["status"] == "accepted"
        client.app.state.waba.send_template.assert_awaited_once()

        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [
                                    {"wa_id": "919888888888", "profile": {"name": "Takeover Test"}}
                                ],
                                "messages": [
                                    {
                                        "from": "919888888888",
                                        "id": "wamid.integration.takeover",
                                        "timestamp": "1793630000",
                                        "type": "text",
                                        "text": {"body": "Need human help"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        webhook_body = json.dumps(webhook_payload).encode()
        webhook_signature = hmac.new(b"app-secret", webhook_body, hashlib.sha256).hexdigest()
        webhook = client.post(
            "/webhook",
            content=webhook_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={webhook_signature}",
            },
        )
        assert webhook.status_code == 200
        conversations = client.get("/api/conversations", headers=headers)
        conversation = next(
            row for row in conversations.json() if row["phone"] == "919888888888"
        )
        takeover = client.post(
            f"/api/conversations/{conversation['id']}/take-over", headers=headers
        )
        assert takeover.status_code == 200
        assert takeover.json()["is_taken_over"] is True
        returned = client.post(
            f"/api/conversations/{conversation['id']}/return-to-bot", headers=headers
        )
        assert returned.status_code == 200
        assert returned.json()["is_taken_over"] is False
