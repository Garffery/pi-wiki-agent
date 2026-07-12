"""Logger configuration for coding-agent using loguru."""

from __future__ import annotations

import os
import sys

from loguru import logger as _loguru_logger

_loguru_logger.remove()

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

_loguru_logger.add(
    sys.stderr,
    format=LOG_FORMAT,
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True,
)

logger = _loguru_logger
