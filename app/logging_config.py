"""Structured (JSON) logging for the retrieve->generate pipeline.

Per docs/ARCHITECTURE.md's Observability section: "Start with structured
logs; add tracing instrumentation once there's a pipeline worth tracing."
No external tracing library — just JSON lines to stdout, which is enough
to answer "what was retrieved, what did the LLM see, how long did each
stage take" for a single-process, single-request pipeline.
"""

import json
import logging
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
        }
        event_data = getattr(record, "event_data", None)
        if event_data:
            payload.update(event_data)
        else:
            payload["message"] = record.getMessage()
        return json.dumps(payload, default=str)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger("archlens")
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"archlens.{name}")


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"event_data": {"event": event, **fields}})
