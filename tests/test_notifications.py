from unittest.mock import AsyncMock

import pytest

from mechman_bot.notifications import NotificationScheduler


def meeting() -> dict:
    return {
        "id": 7,
        "conversation_id": 3,
        "phone": "919999999999",
        "name": "Kunj",
    }


@pytest.mark.asyncio
async def test_free_text_is_blocked_outside_service_window() -> None:
    repository = AsyncMock()
    repository.delivery_exists.return_value = False
    repository.within_service_window.return_value = False
    waba = AsyncMock()
    scheduler = NotificationScheduler(repository, waba)

    with pytest.raises(RuntimeError, match="approved Meta template"):
        await scheduler._send(meeting(), "reminder:60", "Your meeting starts soon")

    waba.send_text.assert_not_awaited()
    repository.add_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_template_can_send_outside_service_window() -> None:
    repository = AsyncMock()
    repository.delivery_exists.return_value = False
    waba = AsyncMock()
    waba.send_template.return_value = "wamid.1"
    scheduler = NotificationScheduler(repository, waba)

    await scheduler._send(
        meeting(),
        "reminder:60",
        "Your meeting starts soon",
        "meeting_reminder",
    )

    waba.send_template.assert_awaited_once_with(
        "919999999999", "meeting_reminder", "en_US", ["Kunj"]
    )
    repository.add_delivery.assert_awaited_once()
