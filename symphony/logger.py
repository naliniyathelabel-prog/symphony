"""Structured JSON logging per SPEC.md §3.1.8."""
from __future__ import annotations
import json, logging, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

class _StructuredFormatter(logging.Formatter):
    def format(self, record):
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = {k: v for k, v in record.__dict__.items()
                 if k not in logging.LogRecord.__dict__ and not k.startswith("_")}
        if extra:
            payload["extra"] = extra
        return json.dumps(payload, default=str)

def configure(log_file=None, level=logging.INFO):
    root = logging.getLogger("symphony")
    root.setLevel(level)
    root.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(_StructuredFormatter())
    root.addHandler(h)
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(p)
        fh.setFormatter(_StructuredFormatter())
        root.addHandler(fh)

def get(name="symphony"):
    return logging.getLogger(name)
