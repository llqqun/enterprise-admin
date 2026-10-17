"""Logging setup (loguru).

Idempotent: each call drops the previous sinks first, so importing the app twice
(as the test suite does) cannot duplicate log lines.
"""

import sys

from loguru import logger

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        settings.LOG_DIR / "backend-{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
        enqueue=True,
        level="DEBUG" if settings.DEBUG else "INFO",
        backtrace=settings.DEBUG,
        # diagnose renders local variable values into tracebacks; keep it off so
        # credentials cannot leak into the log file.
        diagnose=False,
    )
    if settings.DEBUG:
        logger.add(sys.stderr, level="DEBUG", colorize=True)
