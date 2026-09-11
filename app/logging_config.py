"""Structured logging setup shared by the API server and pipeline workers."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger("formai")
    root.setLevel(level)
    root.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_DIR / "formai.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(file_handler)

    # Quiet noisy third-party libraries; we care about our own pipeline logs.
    for noisy in ("ultralytics", "mediapipe", "absl", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"formai.{name}")
