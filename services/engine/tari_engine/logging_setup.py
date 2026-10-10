"""Structured JSON-lines logging for the engine."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": round(time.time(), 3),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in vars(record).items():
            if k not in _RESERVED and not k.startswith("_"):
                try:
                    json.dumps(v)
                    out[k] = v
                except TypeError:
                    out[k] = repr(v)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def configure_logging(level: str = "info", log_dir: Path | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(log_dir / "engine.jsonl", maxBytes=5_000_000, backupCount=3,
                                                  encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel("WARNING")
