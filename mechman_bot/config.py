"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bot_database: Path
    team_alert_number: str
    public_booking_url: str
    jwt_secret: str
    jwt_expire_minutes: int
    admin_username: str
    admin_password: str
    meeting_duration_minutes: int
    log_level: str
    dashboard_auth_enabled: bool = True
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            bot_database=Path(os.environ.get("BOT_DATABASE", "data/mechman-bot.db")).expanduser(),
            team_alert_number=_digits_only(os.environ.get("TEAM_ALERT_NUMBER", "")),
            public_booking_url=os.environ.get(
                "PUBLIC_BOOKING_URL", "http://localhost:5173/book"
            ).rstrip("/"),
            jwt_secret=os.environ.get("JWT_SECRET", ""),
            jwt_expire_minutes=int(os.environ.get("JWT_EXPIRE_MINUTES", "720")),
            admin_username=os.environ.get("ADMIN_USERNAME", "admin"),
            admin_password=os.environ.get("ADMIN_PASSWORD", ""),
            meeting_duration_minutes=int(os.environ.get("MEETING_DURATION_MINUTES", "60")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            dashboard_auth_enabled=os.environ.get("DASHBOARD_AUTH_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"},
            cors_origins=tuple(
                origin.strip().rstrip("/")
                for origin in os.environ.get(
                    "CORS_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
                if origin.strip()
            ),
        )

    def ensure_directories(self) -> None:
        self.bot_database.parent.mkdir(parents=True, exist_ok=True)

    def validate_web(self) -> None:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if len(self.admin_password) < 10:
            raise ValueError("ADMIN_PASSWORD must be at least 10 characters")
        if self.meeting_duration_minutes not in {30, 45, 60, 90, 120}:
            raise ValueError("MEETING_DURATION_MINUTES must be 30, 45, 60, 90, or 120")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain comma-separated HTTP(S) origins")


def _digits_only(value: str) -> str:
    return "".join(character for character in value if character.isdigit())
