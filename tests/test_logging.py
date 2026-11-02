import json
import logging

from mechman_bot.logging_config import JsonFormatter


def test_json_formatter_includes_operational_context() -> None:
    record = logging.LogRecord(
        name="mechman.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.event = "http_request"
    record.request_id = "request-123"
    record.status = 200
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "mechman.access"
    assert payload["request_id"] == "request-123"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 12.5
