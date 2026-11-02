import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from mechman_bot.config import Settings
from mechman_bot.storage import BotStore
from mechman_bot.web import create_app

IST = ZoneInfo("Asia/Kolkata")
PASSWORD = "a-secure-local-password"


def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_database=tmp_path / "bot.db",
        team_alert_number="",
        public_booking_url="http://testserver/book",
        jwt_secret="test-jwt-secret-that-is-longer-than-thirty-two-characters",
        jwt_expire_minutes=60,
        admin_username="admin",
        admin_password=PASSWORD,
        meeting_duration_minutes=60,
        log_level="INFO",
    )


def next_business_day() -> str:
    day = datetime.now(IST).date() + timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day.isoformat()


async def login(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def meeting_payload() -> dict[str, str]:
    return {
        "name": "Raj Patel",
        "phone": "+91 98765 43210",
        "email": "raj@example.com",
        "meeting_date": next_business_day(),
        "start_time": "09:00",
    }


def test_public_booking_and_authenticated_dashboard(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                slots = await client.get("/api/public/slots", params={"date": next_business_day()})
                assert slots.status_code == 200
                assert slots.json()[0]["start_time"] == "09:00"

                created = await client.post("/api/public/meetings", json=meeting_payload())
                assert created.status_code == 201
                assert created.json()["status"] == "requested"

                duplicate = await client.post("/api/public/meetings", json=meeting_payload())
                assert duplicate.status_code == 409

                headers = await login(client)
                analytics = await client.get("/api/dashboard/analytics", headers=headers)
                assert analytics.status_code == 200
                assert analytics.json()["total_meetings"] == 1
                assert analytics.json()["total_contacts"] == 1

                meetings = (await client.get("/api/meetings", headers=headers)).json()
                assert meetings[0]["phone"] == "919876543210"
                assert meetings[0]["email"] == "raj@example.com"
                assert meetings[0]["purpose"] == "Meeting requested through the booking form"

                notification_settings = await client.get(
                    "/api/settings/notifications", headers=headers
                )
                assert notification_settings.status_code == 200
                assert notification_settings.json()["followup_days"] == [1, 3]

                saved_settings = await client.put(
                    "/api/settings/notifications",
                    headers=headers,
                    json={
                        **notification_settings.json(),
                        "reminder_minutes_before": 90,
                        "followup_days": [2, 4],
                    },
                )
                assert saved_settings.status_code == 200
                assert saved_settings.json()["reminder_minutes_before"] == 90
                assert saved_settings.json()["followup_days"] == [2, 4]

                updated = await client.patch(
                    f"/api/meetings/{meetings[0]['id']}",
                    headers=headers,
                    json={"status": "confirmed", "lead_stage": "qualified"},
                )
                assert updated.status_code == 200
                assert updated.json()["status"] == "confirmed"
                assert len(updated.json()["history"]) == 3

    asyncio.run(exercise())


def test_dashboard_routes_require_authentication(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                assert (await client.get("/api/dashboard/analytics")).status_code == 401

    asyncio.run(exercise())


def test_legacy_meeting_table_is_migrated_before_indexes(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE meeting_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_key TEXT NOT NULL,
            phone TEXT NOT NULL,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            purpose TEXT NOT NULL,
            meeting_mode TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            preferred_time TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    store = BotStore(database)
    columns = {
        row["name"] for row in store._connection.execute("PRAGMA table_info(meeting_requests)")
    }
    store.close()

    assert {"start_at", "end_at", "contact_id", "updated_at"}.issubset(columns)
