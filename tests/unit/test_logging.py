from __future__ import annotations

import json
import logging

from graphrag_service.logging import JsonFormatter, request_id_context


def test_json_logging_redacts_sensitive_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.service_token = "do-not-log-me"
    record.details = {"password": "also-secret", "safe": "visible"}
    token = request_id_context.set("request-123")
    try:
        payload = json.loads(formatter.format(record))
    finally:
        request_id_context.reset(token)

    assert payload["request_id"] == "request-123"
    assert payload["service_token"] == "[REDACTED]"
    assert payload["details"]["password"] == "[REDACTED]"
    assert payload["details"]["safe"] == "visible"
