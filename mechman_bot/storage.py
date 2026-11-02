"""Thread-safe SQLite persistence for bot state, CRM contacts, and meetings."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BotStore:
    """Single-process SQLite repository for CRM, booking, and message state."""

    def __init__(self, database: str | Path = "data/mechman_bot.db") -> None:
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if self.database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_state (
                    chat_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL UNIQUE,
                    email TEXT,
                    company TEXT,
                    designation TEXT,
                    city TEXT,
                    lead_stage TEXT NOT NULL DEFAULT 'new',
                    source TEXT NOT NULL DEFAULT 'web_form',
                    assigned_to TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meeting_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER REFERENCES contacts(id),
                    chat_key TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT,
                    company TEXT NOT NULL DEFAULT '',
                    designation TEXT,
                    city TEXT,
                    interest TEXT,
                    purpose TEXT NOT NULL,
                    meeting_mode TEXT NOT NULL,
                    start_at TEXT,
                    end_at TEXT,
                    preferred_date TEXT NOT NULL DEFAULT '',
                    preferred_time TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'requested',
                    lead_stage TEXT NOT NULL DEFAULT 'new',
                    source TEXT NOT NULL DEFAULT 'whatsapp',
                    assigned_to TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meeting_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id INTEGER NOT NULL REFERENCES meeting_requests(id),
                    action TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    changed_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id INTEGER NOT NULL REFERENCES meeting_requests(id),
                    notification_key TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    UNIQUE(meeting_id, notification_key)
                );
                CREATE INDEX IF NOT EXISTS idx_contacts_stage ON contacts(lead_stage);
                """
            )
            self._migrate_legacy_meetings()
            self._connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_meetings_start ON meeting_requests(start_at);
                CREATE INDEX IF NOT EXISTS idx_meetings_status ON meeting_requests(status);
                CREATE INDEX IF NOT EXISTS idx_meetings_contact ON meeting_requests(contact_id);
                CREATE INDEX IF NOT EXISTS idx_notifications_meeting
                    ON notification_deliveries(meeting_id);
                """
            )
            self._seed_notification_settings()

    def _seed_notification_settings(self) -> None:
        now = _now()
        defaults = {
            "reminder_enabled": "true",
            "reminder_minutes_before": "60",
            "followup_enabled": "true",
            "followup_days": "[1,3]",
            "reminder_template": (
                "Hi {name}, a quick reminder from Mechman Solutions — your meeting is "
                "scheduled for {date} at {time} IST. See you in about {minutes} minutes. "
                "If you need to reschedule, just reply here."
            ),
            "followup_template": (
                "Hi {name}, following up {days} day(s) after our Mechman Solutions meeting "
                "on {date}. Is there anything you would like us to clarify or prepare for "
                "the next step? Reply here anytime."
            ),
        }
        self._connection.executemany(
            "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            [(key, value, now) for key, value in defaults.items()],
        )

    def _migrate_legacy_meetings(self) -> None:
        existing = {
            row["name"] for row in self._connection.execute("PRAGMA table_info(meeting_requests)")
        }
        additions = {
            "contact_id": "INTEGER REFERENCES contacts(id)",
            "email": "TEXT",
            "designation": "TEXT",
            "city": "TEXT",
            "interest": "TEXT",
            "start_at": "TEXT",
            "end_at": "TEXT",
            "lead_stage": "TEXT NOT NULL DEFAULT 'new'",
            "source": "TEXT NOT NULL DEFAULT 'whatsapp'",
            "assigned_to": "TEXT",
            "notes": "TEXT",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, declaration in additions.items():
            if name not in existing:
                self._connection.execute(
                    f"ALTER TABLE meeting_requests ADD COLUMN {name} {declaration}"
                )

    def get_state(self, chat_key: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM conversation_state WHERE chat_key = ?", (chat_key,)
            ).fetchone()
        if row is None:
            return {"stage": "menu", "lead": {}, "context": {}}
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return {"stage": "menu", "lead": {}, "context": {}}
        payload.setdefault("stage", "menu")
        payload.setdefault("lead", {})
        payload.setdefault("context", {})
        return payload

    def save_state(self, chat_key: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO conversation_state (chat_key, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_key) DO UPDATE SET
                    payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
                """,
                (chat_key, payload),
            )

    def reset_state(self, chat_key: str) -> None:
        self.save_state(chat_key, {"stage": "menu", "lead": {}, "context": {}})

    def create_admin_if_missing(
        self, username: str, password_hash: str, full_name: str = "Mechman Admin"
    ) -> None:
        now = _now()
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO users
                    (username, full_name, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 'admin', 1, ?, ?)
                """,
                (username, full_name, password_hash, now, now),
            )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM users WHERE lower(username) = lower(?)", (username,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def _upsert_contact(self, data: dict[str, Any]) -> int:
        phone = str(data.get("phone", ""))
        now = _now()
        row = self._connection.execute(
            "SELECT id FROM contacts WHERE phone = ?", (phone,)
        ).fetchone()
        values = (
            str(data.get("name", "")),
            data.get("email"),
            data.get("company"),
            data.get("designation"),
            data.get("city"),
            str(data.get("source", "web_form")),
            now,
        )
        if row:
            self._connection.execute(
                """
                UPDATE contacts SET
                    name = ?, email = COALESCE(?, email), company = COALESCE(?, company),
                    designation = COALESCE(?, designation), city = COALESCE(?, city),
                    source = ?, updated_at = ? WHERE id = ?
                """,
                (*values, row["id"]),
            )
            return int(row["id"])
        cursor = self._connection.execute(
            """
            INSERT INTO contacts
                (name, phone, email, company, designation, city, lead_stage,
                 source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
            """,
            (
                data.get("name", ""),
                phone,
                data.get("email"),
                data.get("company"),
                data.get("designation"),
                data.get("city"),
                data.get("source", "web_form"),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def add_meeting(self, chat_key: str, phone: str, lead: dict[str, str]) -> int:
        return self.create_meeting(
            {
                "name": lead.get("name", ""),
                "phone": phone,
                "company": lead.get("company", ""),
                "purpose": lead.get("purpose", ""),
                "meeting_mode": lead.get("mode", ""),
                "preferred_date": lead.get("date", ""),
                "preferred_time": lead.get("time", ""),
                "source": "whatsapp",
                "chat_key": chat_key,
            }
        )

    def create_meeting(self, data: dict[str, Any]) -> int:
        now = _now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if data.get("start_at") and data.get("end_at"):
                    occupied = self._connection.execute(
                        """
                        SELECT 1 FROM meeting_requests
                        WHERE status IN ('requested', 'confirmed', 'scheduled')
                          AND start_at < ? AND end_at > ? LIMIT 1
                        """,
                        (data["end_at"], data["start_at"]),
                    ).fetchone()
                    if occupied:
                        raise ValueError("That slot was just booked. Please choose another time.")
                contact_id = self._upsert_contact(data)
                cursor = self._connection.execute(
                    """
                    INSERT INTO meeting_requests (
                        contact_id, chat_key, phone, name, email, company, designation,
                        city, interest, purpose, meeting_mode, start_at, end_at,
                        preferred_date, preferred_time, status, lead_stage, source,
                        assigned_to, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested',
                              'new', ?, ?, ?, ?, ?)
                    """,
                    (
                        contact_id,
                        data.get("chat_key", ""),
                        data.get("phone", ""),
                        data.get("name", ""),
                        data.get("email"),
                        data.get("company", ""),
                        data.get("designation"),
                        data.get("city"),
                        data.get("interest"),
                        data.get("purpose", ""),
                        data.get("meeting_mode", ""),
                        data.get("start_at"),
                        data.get("end_at"),
                        data.get("preferred_date", ""),
                        data.get("preferred_time", ""),
                        data.get("source", "web_form"),
                        data.get("assigned_to"),
                        data.get("notes"),
                        now,
                        now,
                    ),
                )
                meeting_id = int(cursor.lastrowid)
                self._add_history(
                    meeting_id, "created", None, "requested", data.get("source", "system")
                )
                self._connection.execute("COMMIT")
                return meeting_id
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _add_history(
        self,
        meeting_id: int,
        action: str,
        old_value: str | None,
        new_value: str | None,
        changed_by: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO meeting_history
                (meeting_id, action, old_value, new_value, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (meeting_id, action, old_value, new_value, changed_by, _now()),
        )

    def list_meetings(
        self,
        *,
        query: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if query:
            conditions.append("(name LIKE ? OR phone LIKE ? OR company LIKE ? OR purpose LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if status:
            conditions.append("status = ?")
            params.append(status)
        if date_from:
            conditions.append("start_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("start_at <= ?")
            params.append(date_to)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(min(max(limit, 1), 500))
        with self._lock:
            rows = self._connection.execute(
                f"""SELECT * FROM meeting_requests {where}
                ORDER BY COALESCE(start_at, created_at) DESC LIMIT ?""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_meeting(self, meeting_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM meeting_requests WHERE id = ?", (meeting_id,)
            ).fetchone()
            if not row:
                return None
            history = self._connection.execute(
                "SELECT * FROM meeting_history WHERE meeting_id = ? ORDER BY id DESC",
                (meeting_id,),
            ).fetchall()
        result = dict(row)
        result["history"] = [dict(item) for item in history]
        return result

    def update_meeting(
        self, meeting_id: int, changes: dict[str, Any], changed_by: str
    ) -> dict[str, Any] | None:
        allowed = {"status", "lead_stage", "assigned_to", "notes", "start_at", "end_at"}
        clean = {key: value for key, value in changes.items() if key in allowed}
        if not clean:
            return self.get_meeting(meeting_id)
        with self._lock:
            current = self._connection.execute(
                "SELECT * FROM meeting_requests WHERE id = ?", (meeting_id,)
            ).fetchone()
            if not current:
                return None
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for key, value in clean.items():
                    old = current[key]
                    if old == value:
                        continue
                    self._connection.execute(
                        f"UPDATE meeting_requests SET {key} = ?, updated_at = ? WHERE id = ?",
                        (value, _now(), meeting_id),
                    )
                    self._add_history(meeting_id, key, str(old or ""), str(value or ""), changed_by)
                if "lead_stage" in clean and current["contact_id"]:
                    self._connection.execute(
                        "UPDATE contacts SET lead_stage = ?, updated_at = ? WHERE id = ?",
                        (clean["lead_stage"], _now(), current["contact_id"]),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.get_meeting(meeting_id)

    def busy_ranges(self, start_at: str, end_at: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT start_at, end_at FROM meeting_requests
                WHERE status IN ('requested', 'confirmed', 'scheduled')
                  AND start_at IS NOT NULL AND start_at < ? AND end_at > ?
                ORDER BY start_at
                """,
                (end_at, start_at),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_contacts(self, query: str = "") -> list[dict[str, Any]]:
        params: list[Any] = [_now()]
        where = ""
        if query:
            where = "WHERE c.name LIKE ? OR c.phone LIKE ? OR c.company LIKE ?"
            like = f"%{query}%"
            params.extend([like, like, like])
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT c.*, COUNT(m.id) AS meeting_count,
                       MAX(m.created_at) AS last_activity,
                       MIN(CASE WHEN m.start_at >= ? AND m.status IN ('requested','confirmed','scheduled')
                                THEN m.start_at END) AS next_meeting
                FROM contacts c LEFT JOIN meeting_requests m ON m.contact_id = c.id
                {where} GROUP BY c.id
                ORDER BY COALESCE(last_activity, c.created_at) DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
            if not row:
                return None
            meetings = self._connection.execute(
                "SELECT * FROM meeting_requests WHERE contact_id = ? ORDER BY created_at DESC",
                (contact_id,),
            ).fetchall()
        result = dict(row)
        result["meetings"] = [dict(item) for item in meetings]
        return result

    def analytics(self) -> dict[str, Any]:
        today = datetime.now().date().isoformat()
        with self._lock:
            total_contacts = self._connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            total_meetings = self._connection.execute(
                "SELECT COUNT(*) FROM meeting_requests"
            ).fetchone()[0]
            upcoming = self._connection.execute(
                """SELECT COUNT(*) FROM meeting_requests
                WHERE start_at >= ? AND status IN ('requested','confirmed','scheduled')""",
                (today,),
            ).fetchone()[0]
            today_count = self._connection.execute(
                "SELECT COUNT(*) FROM meeting_requests WHERE substr(start_at,1,10) = ?",
                (today,),
            ).fetchone()[0]
            status_rows = self._connection.execute(
                "SELECT status, COUNT(*) AS count FROM meeting_requests GROUP BY status"
            ).fetchall()
            source_rows = self._connection.execute(
                "SELECT source, COUNT(*) AS count FROM meeting_requests GROUP BY source"
            ).fetchall()
            interest_rows = self._connection.execute(
                """SELECT COALESCE(interest, 'General enquiry') AS interest, COUNT(*) AS count
                FROM meeting_requests GROUP BY COALESCE(interest, 'General enquiry')
                ORDER BY count DESC LIMIT 8"""
            ).fetchall()
            monthly_rows = self._connection.execute(
                """SELECT substr(created_at,1,7) AS month, COUNT(*) AS count
                FROM meeting_requests GROUP BY substr(created_at,1,7)
                ORDER BY month DESC LIMIT 6"""
            ).fetchall()
            recent = self._connection.execute(
                "SELECT * FROM meeting_requests ORDER BY created_at DESC LIMIT 6"
            ).fetchall()
        return {
            "total_contacts": total_contacts,
            "total_meetings": total_meetings,
            "upcoming_meetings": upcoming,
            "today_meetings": today_count,
            "by_status": [dict(row) for row in status_rows],
            "by_source": [dict(row) for row in source_rows],
            "by_interest": [dict(row) for row in interest_rows],
            "monthly_trend": list(reversed([dict(row) for row in monthly_rows])),
            "recent_meetings": [dict(row) for row in recent],
        }

    def get_notification_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute("SELECT key, value FROM app_settings").fetchall()
        raw = {row["key"]: row["value"] for row in rows}
        try:
            followup_days = json.loads(raw.get("followup_days", "[1,3]"))
        except json.JSONDecodeError:
            followup_days = [1, 3]
        return {
            "reminder_enabled": raw.get("reminder_enabled", "true") == "true",
            "reminder_minutes_before": int(raw.get("reminder_minutes_before", "60")),
            "followup_enabled": raw.get("followup_enabled", "true") == "true",
            "followup_days": followup_days,
            "reminder_template": raw.get("reminder_template", ""),
            "followup_template": raw.get("followup_template", ""),
        }

    def update_notification_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        serialized = {
            "reminder_enabled": str(bool(values["reminder_enabled"])).lower(),
            "reminder_minutes_before": str(values["reminder_minutes_before"]),
            "followup_enabled": str(bool(values["followup_enabled"])).lower(),
            "followup_days": json.dumps(values["followup_days"], separators=(",", ":")),
            "reminder_template": str(values["reminder_template"]),
            "followup_template": str(values["followup_template"]),
        }
        now = _now()
        with self._lock:
            self._connection.executemany(
                """
                INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                [(key, value, now) for key, value in serialized.items()],
            )
        return self.get_notification_settings()

    def due_notifications(self, now: datetime) -> list[dict[str, Any]]:
        settings = self.get_notification_settings()
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT m.* FROM meeting_requests m
                WHERE m.start_at IS NOT NULL AND m.phone != ''
                  AND m.status IN ('confirmed', 'scheduled', 'completed')
                ORDER BY m.start_at
                """
            ).fetchall()
            delivered_rows = self._connection.execute(
                "SELECT meeting_id, notification_key FROM notification_deliveries"
            ).fetchall()
        delivered = {(row["meeting_id"], row["notification_key"]) for row in delivered_rows}
        jobs: list[dict[str, Any]] = []
        for row in rows:
            meeting = dict(row)
            try:
                starts = datetime.fromisoformat(str(meeting["start_at"]))
            except ValueError:
                continue
            local_now = now.astimezone(starts.tzinfo or timezone.utc)
            context = {
                "name": meeting["name"],
                "date": starts.strftime("%A, %d %B %Y"),
                "time": starts.strftime("%-I:%M %p"),
                "minutes": settings["reminder_minutes_before"],
                "days": 0,
            }
            reminder_key = f"reminder_{settings['reminder_minutes_before']}m"
            reminder_due = starts - timedelta(minutes=settings["reminder_minutes_before"])
            if (
                settings["reminder_enabled"]
                and meeting["status"] in {"confirmed", "scheduled"}
                and reminder_due <= local_now < starts
                and (meeting["id"], reminder_key) not in delivered
            ):
                jobs.append(
                    {
                        "meeting_id": meeting["id"],
                        "notification_key": reminder_key,
                        "phone": meeting["phone"],
                        "message": settings["reminder_template"].format(**context),
                    }
                )
            if settings["followup_enabled"]:
                for days in settings["followup_days"]:
                    followup_key = f"followup_{days}d"
                    if (
                        local_now >= starts + timedelta(days=days)
                        and (meeting["id"], followup_key) not in delivered
                    ):
                        jobs.append(
                            {
                                "meeting_id": meeting["id"],
                                "notification_key": followup_key,
                                "phone": meeting["phone"],
                                "message": settings["followup_template"].format(
                                    **{**context, "days": days}
                                ),
                            }
                        )
        return jobs

    def mark_notification_sent(self, job: dict[str, Any]) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO notification_deliveries
                    (meeting_id, notification_key, recipient, message, sent_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job["meeting_id"],
                    job["notification_key"],
                    job["phone"],
                    job["message"],
                    _now(),
                ),
            )

    def recent_notification_deliveries(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT d.*, m.name, m.start_at FROM notification_deliveries d
                JOIN meeting_requests m ON m.id = d.meeting_id
                ORDER BY d.sent_at DESC LIMIT ?
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_message(self, message_id: str) -> bool:
        if not message_id:
            return True
        with self._lock:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (message_id,)
            )
            return cursor.rowcount == 1

    def close(self) -> None:
        with self._lock:
            self._connection.close()
