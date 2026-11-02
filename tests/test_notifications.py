from datetime import datetime, timedelta, timezone

from mechman_bot.notifications import NotificationScheduler
from mechman_bot.storage import BotStore


def create_scheduled_meeting(store: BotStore, starts: datetime) -> int:
    meeting_id = store.create_meeting(
        {
            "name": "Raj Patel",
            "phone": "919876543210",
            "email": "raj@example.com",
            "company": "",
            "purpose": "Meeting requested through the booking form",
            "meeting_mode": "WhatsApp or phone call",
            "start_at": starts.isoformat(),
            "end_at": (starts + timedelta(hours=1)).isoformat(),
            "preferred_date": starts.date().isoformat(),
            "preferred_time": starts.strftime("%H:%M"),
            "source": "web_form",
        }
    )
    store.update_meeting(meeting_id, {"status": "confirmed"}, "test")
    return meeting_id


def test_scheduler_sends_reminder_once_and_persists_delivery() -> None:
    store = BotStore(":memory:")
    now = datetime(2027, 1, 12, 8, 30, tzinfo=timezone.utc)
    create_scheduled_meeting(store, now + timedelta(minutes=45))
    sent: list[tuple[str, str]] = []
    scheduler = NotificationScheduler(
        store,
        lambda phone, message: sent.append((phone, message)),
    )

    assert scheduler.run_once(now) == 1
    assert scheduler.run_once(now + timedelta(minutes=5)) == 0
    assert sent[0][0] == "919876543210"
    assert "quick reminder" in sent[0][1]
    assert len(store.recent_notification_deliveries()) == 1
    store.close()


def test_followup_days_are_configurable() -> None:
    store = BotStore(":memory:")
    starts = datetime(2027, 1, 12, 8, 30, tzinfo=timezone.utc)
    meeting_id = create_scheduled_meeting(store, starts)
    store.update_meeting(meeting_id, {"status": "completed"}, "test")
    current = store.get_notification_settings()
    store.update_notification_settings({**current, "followup_days": [2, 4]})

    jobs = store.due_notifications(starts + timedelta(days=2, minutes=1))

    assert [job["notification_key"] for job in jobs] == ["followup_2d"]
    assert "2 day(s)" in jobs[0]["message"]
    store.close()


def test_scheduler_waits_for_transport_availability() -> None:
    store = BotStore(":memory:")
    now = datetime(2027, 1, 12, 8, 30, tzinfo=timezone.utc)
    create_scheduled_meeting(store, now + timedelta(minutes=30))
    sent: list[tuple[str, str]] = []
    scheduler = NotificationScheduler(
        store,
        lambda phone, message: sent.append((phone, message)),
        is_available=lambda: False,
    )

    assert scheduler.run_once(now) == 0
    assert sent == []
    store.close()
