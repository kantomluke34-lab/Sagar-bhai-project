"""Environment-backed configuration for the Mechman CRM."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_booking_url: str
    frontend_origin: str
    jwt_secret: str
    jwt_expire_minutes: int
    admin_username: str
    admin_password: str
    meeting_duration_minutes: int
    log_level: str
    meta_access_token: str
    meta_phone_number_id: str
    meta_waba_id: str
    meta_api_version: str
    meta_webhook_verify_token: str
    meta_app_secret: str
    meta_app_id: str = ""
    dashboard_auth_enabled: bool = True
    notification_poll_seconds: int = 30
    campaign_poll_seconds: int = 10
    media_root: str = "/app/media"
    max_media_bytes: int = 100 * 1024 * 1024
    log_format: str = "json"
    slow_request_ms: int = 1000
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @classmethod
    def from_environment(cls) -> Settings:
        frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql+asyncpg://mechman:mechman@localhost:5432/mechman",
            ),
            public_booking_url=os.environ.get(
                "PUBLIC_BOOKING_URL", f"{frontend_origin}/book"
            ).rstrip("/"),
            frontend_origin=frontend_origin,
            jwt_secret=os.environ.get("JWT_SECRET", ""),
            jwt_expire_minutes=int(os.environ.get("JWT_EXPIRE_MINUTES", "720")),
            admin_username=os.environ.get("ADMIN_USERNAME", "admin"),
            admin_password=os.environ.get("ADMIN_PASSWORD", ""),
            meeting_duration_minutes=int(os.environ.get("MEETING_DURATION_MINUTES", "60")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            meta_access_token=os.environ.get(
                "WHATSAPP_ACCESS_TOKEN", os.environ.get("META_ACCESS_TOKEN", "")
            ),
            meta_app_id=os.environ.get("META_APP_ID") or "2545072705904292",
            meta_phone_number_id=os.environ.get("META_PHONE_NUMBER_ID", "1395187090344267"),
            meta_waba_id=os.environ.get("META_WABA_ID", "29459993996925480"),
            meta_api_version=os.environ.get("META_API_VERSION", "v26.0"),
            meta_webhook_verify_token=os.environ.get(
                "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
                os.environ.get("META_WEBHOOK_VERIFY_TOKEN", ""),
            ),
            meta_app_secret=os.environ.get("META_APP_SECRET", ""),
            dashboard_auth_enabled=_truthy("DASHBOARD_AUTH_ENABLED", "true"),
            notification_poll_seconds=max(
                10, int(os.environ.get("NOTIFICATION_POLL_SECONDS", "30"))
            ),
            campaign_poll_seconds=max(5, int(os.environ.get("CAMPAIGN_POLL_SECONDS", "10"))),
            media_root=os.environ.get("MEDIA_ROOT", "/app/media"),
            max_media_bytes=max(
                1024 * 1024, int(os.environ.get("MAX_MEDIA_BYTES", str(100 * 1024 * 1024)))
            ),
            log_format=os.environ.get("LOG_FORMAT", "json").lower(),
            slow_request_ms=max(100, int(os.environ.get("SLOW_REQUEST_MS", "1000"))),
            cors_origins=tuple(
                origin.strip().rstrip("/")
                for origin in os.environ.get(
                    "CORS_ORIGINS",
                    f"{frontend_origin},http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
                if origin.strip()
            ),
        )

    @property
    def waba_configured(self) -> bool:
        return bool(self.meta_access_token and self.meta_phone_number_id)

    def validate_web(self) -> None:
        if not self.database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if len(self.admin_password) < 10:
            raise ValueError("ADMIN_PASSWORD must be at least 10 characters")
        if self.meeting_duration_minutes not in {30, 45, 60, 90, 120}:
            raise ValueError("MEETING_DURATION_MINUTES must be 30, 45, 60, 90, or 120")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain comma-separated HTTP(S) origins")
        if self.log_format not in {"json", "text"}:
            raise ValueError("LOG_FORMAT must be json or text")


settings = Settings.from_environment()
