"""Structured JSON logging (PRD §18). Never log transcripts or phone numbers (NFR-S8)."""

import json
import logging
import sys
from typing import Any

_FIELDS = (
    "incident_id",
    "resident_id",
    "event_type",
    "actor",
    "tool",
    "status_from",
    "status_to",
    "latency_ms",
    "model",
    "fallback_used",
    "error_code",
    "job",
)


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line, compatible with Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for f in _FIELDS:
            if hasattr(record, f):
                out[f] = getattr(record, f)
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger. Pass structured fields via `extra={...}`."""
    return logging.getLogger(name)
