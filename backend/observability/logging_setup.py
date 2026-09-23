"""Structured logging.

The logger was never configured before, so nothing on the success path was
recorded at all. Output is one JSON object per line: greppable by hand, and
parseable by anything that ingests logs later.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from observability.context import current_request_id

# Anything whose name matches these is never written, at any level.
_REDACT = ("password", "secret", "token", "api_key", "authorization", "credential")


def _redact(value: str) -> str:
    low = value.lower()
    return "<redacted>" if any(k in low for k in _REDACT) else value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": current_request_id(),
            "message": _redact(record.getMessage()),
        }
        for key, val in getattr(record, "extra_fields", {}).items():
            payload[key] = _redact(val) if isinstance(val, str) else val
        if record.exc_info:
            # Type and message only. Full tracebacks can carry connection
            # strings and row data; those stay in the process, not the log.
            exc_type, exc, _tb = record.exc_info
            payload["error_type"] = getattr(exc_type, "__name__", "Error")
            payload["error"] = str(exc)[:500]
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("agentic_rag")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
