import os
from datetime import date, timedelta

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
