from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mechman_bot.api import build_router
from mechman_bot.config import Settings


def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        public_booking_url="https://example.com/book",
        frontend_origin="https://example.com",
        jwt_secret="x" * 32,
        jwt_expire_minutes=60,
        admin_username="admin",
        admin_password="password-password",
        meeting_duration_minutes=60,
        log_level="INFO",
        meta_access_token="token",
        meta_phone_number_id="phone-id",
        meta_waba_id="waba-id",
        meta_api_version="v26.0",
        meta_webhook_verify_token="verify",
        meta_app_secret="secret",
        dashboard_auth_enabled=False,
    )


def client_for(repository, waba) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(settings(), repository, waba))
    return TestClient(app)


def admin_repository(**overrides):
    values = {
        "get_user_by_username": AsyncMock(
            return_value={
                "id": 1,
                "username": "admin",
                "full_name": "Administrator",
                "role": "admin",
                "is_active": True,
            }
        ),
        "begin_template_submission": AsyncMock(
            return_value={"id": 7, "name": "welcome", "status": "SUBMITTING"}
        ),
        "update_template": AsyncMock(
            return_value={"id": 7, "name": "welcome", "status": "PENDING"}
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_template_submission_conflict_does_not_call_meta() -> None:
    repository = admin_repository(
        begin_template_submission=AsyncMock(
            return_value={"id": 7, "status": "PENDING", "submission_conflict": True}
        )
    )
    waba = SimpleNamespace(submit_template=AsyncMock())

    response = client_for(repository, waba).post("/api/templates/7/submit")

    assert response.status_code == 409
    waba.submit_template.assert_not_awaited()


def test_non_admin_cannot_mutate_templates() -> None:
    repository = admin_repository()
    repository.get_user_by_username.return_value = {
        "id": 2,
        "username": "viewer",
        "full_name": "Viewer",
        "role": "viewer",
        "is_active": True,
    }
    waba = SimpleNamespace()

    response = client_for(repository, waba).post(
        "/api/templates",
        json={"name": "welcome", "body": "Hello", "variables": []},
    )

    assert response.status_code == 403


def test_campaign_creation_requires_idempotency_key() -> None:
    repository = admin_repository()
    waba = SimpleNamespace()

    response = client_for(repository, waba).post(
        "/api/campaigns",
        json={
            "name": "Safe campaign",
            "template_id": 1,
            "source_type": "paste",
            "recipients": [{"phone": "919876543210", "variables": {}}],
            "consent_confirmed": True,
            "consent_source": "test",
            "consent_captured_at": "2027-01-01T10:00:00+05:30",
            "consent_evidence": "test evidence",
            "scheduled_at": "2027-01-01T10:30:00+05:30",
        },
    )

    assert response.status_code == 422
    assert any(item["loc"][-1] == "Idempotency-Key" for item in response.json()["detail"])
