import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from mechman_bot.config import Settings
from mechman_bot.web import create_app

IST = ZoneInfo("Asia/Kolkata")
PASSWORD = "production-readiness-password"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_database=tmp_path / "crm.db",
        team_alert_number="",
        public_booking_url="http://testserver/book",
        jwt_secret="production-readiness-secret-longer-than-thirty-two-characters",
        jwt_expire_minutes=60,
        admin_username="admin",
        admin_password=PASSWORD,
        meeting_duration_minutes=60,
        log_level="INFO",
        cors_origins=("https://mechman-demo.vercel.app",),
    )


def _business_days(count: int) -> list[str]:
    result: list[str] = []
    day = datetime.now(IST).date() + timedelta(days=1)
    while len(result) < count:
        if day.weekday() != 6:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def test_all_dashboard_api_workflows_and_validation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                protected = [
                    "/api/auth/me",
                    "/api/dashboard/analytics",
                    "/api/meetings",
                    "/api/crm/contacts",
                    "/api/settings/notifications",
                    "/api/settings/notifications/deliveries",
                ]
                for path in protected:
                    assert (await client.get(path)).status_code == 401, path

                assert (await client.get("/healthz")).json() == {"status": "ok"}
                config = await client.get("/api/public/config")
                assert config.status_code == 200
                assert config.json()["timezone"] == "Asia/Kolkata"
                preflight = await client.options(
                    "/api/public/config",
                    headers={
                        "Origin": "https://mechman-demo.vercel.app",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert preflight.status_code == 200
                assert (
                    preflight.headers["access-control-allow-origin"]
                    == "https://mechman-demo.vercel.app"
                )

                invalid_login = await client.post(
                    "/api/auth/login", json={"username": "admin", "password": "incorrect"}
                )
                assert invalid_login.status_code == 401
                login = await client.post(
                    "/api/auth/login", json={"username": "admin", "password": PASSWORD}
                )
                assert login.status_code == 200
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                assert (await client.get("/api/auth/me", headers=headers)).json()["role"] == "admin"

                bad_email = await client.post(
                    "/api/public/meetings",
                    json={
                        "name": "Test User",
                        "phone": "9876543210",
                        "email": "invalid",
                        "meeting_date": _business_days(1)[0],
                        "start_time": "09:00",
                    },
                )
                assert bad_email.status_code == 422

                day = _business_days(1)[0]
                payload = {
                    "name": "Asha Shah",
                    "phone": "+91 98765 00001",
                    "email": "asha@example.com",
                    "meeting_date": day,
                    "start_time": "09:00",
                }
                created = await client.post("/api/public/meetings", json=payload)
                assert created.status_code == 201
                meeting_id = created.json()["meeting_id"]
                assert (await client.post("/api/public/meetings", json=payload)).status_code == 409

                filtered = await client.get(
                    "/api/meetings", headers=headers, params={"q": "Asha", "status": "requested"}
                )
                assert [row["id"] for row in filtered.json()] == [meeting_id]
                assert not (
                    await client.get("/api/meetings", headers=headers, params={"q": "missing"})
                ).json()

                detail = await client.get(f"/api/meetings/{meeting_id}", headers=headers)
                assert detail.status_code == 200
                assert detail.json()["history"][0]["action"] == "created"
                assert (await client.get("/api/meetings/99999", headers=headers)).status_code == 404

                invalid_update = await client.patch(
                    f"/api/meetings/{meeting_id}", headers=headers, json={"status": "invalid"}
                )
                assert invalid_update.status_code == 422
                updated = await client.patch(
                    f"/api/meetings/{meeting_id}",
                    headers=headers,
                    json={
                        "status": "confirmed",
                        "lead_stage": "qualified",
                        "assigned_to": "Kiran",
                        "notes": "Qualified during QA",
                    },
                )
                assert updated.status_code == 200
                assert updated.json()["status"] == "confirmed"
                assert updated.json()["lead_stage"] == "qualified"
                assert len(updated.json()["history"]) == 5

                contacts = await client.get(
                    "/api/crm/contacts", headers=headers, params={"q": "Asha"}
                )
                assert len(contacts.json()) == 1
                contact_id = contacts.json()[0]["id"]
                contact = await client.get(f"/api/crm/contacts/{contact_id}", headers=headers)
                assert contact.status_code == 200
                assert contact.json()["lead_stage"] == "qualified"
                assert len(contact.json()["meetings"]) == 1
                assert (
                    await client.get("/api/crm/contacts/99999", headers=headers)
                ).status_code == 404

                settings = (await client.get("/api/settings/notifications", headers=headers)).json()
                invalid_settings = await client.put(
                    "/api/settings/notifications",
                    headers=headers,
                    json={**settings, "reminder_template": "Bad {unknown} placeholder"},
                )
                assert invalid_settings.status_code == 422
                saved = await client.put(
                    "/api/settings/notifications",
                    headers=headers,
                    json={**settings, "reminder_minutes_before": 90, "followup_days": [3, 1, 3]},
                )
                assert saved.status_code == 200
                assert saved.json()["reminder_minutes_before"] == 90
                assert saved.json()["followup_days"] == [1, 3]

                analytics = await client.get("/api/dashboard/analytics", headers=headers)
                assert analytics.status_code == 200
                assert analytics.json()["total_contacts"] == 1
                assert analytics.json()["total_meetings"] == 1
                assert analytics.json()["by_status"] == [{"status": "confirmed", "count": 1}]

    asyncio.run(exercise())
