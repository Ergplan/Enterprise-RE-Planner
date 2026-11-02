"""JSON log lines for the service: time, level, logger, message, and nothing else. The
message itself only ever carries ids, hashes, counts, timings and check ids (invariant 9)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            line["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(line, ensure_ascii=False)
