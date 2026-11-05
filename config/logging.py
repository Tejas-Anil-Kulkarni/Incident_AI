"""Small structured-logging setup shared by the API and later workers."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render log records as machine-readable JSON without exposing secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once, preserving host-provided handlers."""

    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(handler, "_incidentmind", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler._incidentmind = True  # type: ignore[attr-defined]
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)

