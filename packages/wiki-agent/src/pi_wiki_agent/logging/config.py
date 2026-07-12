"""Logger configuration for wiki-agent using loguru.

On import, a console sink (stderr, colorized) is set up at the level specified
by the LOG_LEVEL env var (default INFO).  Call ``configure()`` later to add
file logging or adjust levels.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger as _loguru_logger

# ── remove default handler ────────────────────────────────────────────────
_loguru_logger.remove()

# ── format ────────────────────────────────────────────────────────────────
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# ── initial console sink ──────────────────────────────────────────────────
_loguru_logger.add(
    sys.stderr,
    format=LOG_FORMAT,
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True,
)

# ── public exports ─────────────────────────────────────────────────────────
logger = _loguru_logger
"""Pre-configured loguru logger. Import and use directly."""


@dataclass
class LoggerConfig:
    """Immutable snapshot of current logger configuration (for introspection)."""

    console_level: str = "INFO"
    file_level: str = "DEBUG"
    log_dir: str = ""


def configure(
    project_root: str | Path | None = None,
    *,
    level: str | None = None,
    file_level: str | None = None,
    log_dir: str | Path | None = None,
) -> LoggerConfig:
    """Configure (or reconfigure) wiki-agent logging.

    Must be called at least once with a ``project_root`` or ``log_dir`` to
    enable file logging.  Safe to call multiple times — previous sinks are
    discarded.

    Args:
        project_root: Project root.  File logs go to ``<root>/.wiki/logs/``.
        level: Console log level (env ``LOG_LEVEL``, default ``INFO``).
        file_level: File log level (env ``LOG_FILE_LEVEL``, default ``DEBUG``).
        log_dir: Explicit log directory (overrides the project-root default).

    Returns:
        ``LoggerConfig`` describing the applied configuration.
    """
    console_level = level or os.getenv("LOG_LEVEL", "INFO")
    file_lvl = file_level or os.getenv("LOG_FILE_LEVEL", "DEBUG")

    _loguru_logger.remove()

    # Console sink
    _loguru_logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=console_level.upper(),
        colorize=True,
    )

    # Resolve log directory for file sink
    resolved: Path | None = None
    if log_dir:
        resolved = Path(log_dir)
    elif project_root:
        resolved = Path(project_root) / ".wiki" / "logs"

    cfg = LoggerConfig(console_level=console_level, file_level=file_lvl)

    if resolved:
        resolved.mkdir(parents=True, exist_ok=True)
        log_file = resolved / "wiki-agent.{time:YYYY-MM-DD}.log"
        _loguru_logger.add(
            str(log_file),
            format=LOG_FORMAT,
            level=file_lvl.upper(),
            rotation="10 MB",
            retention="7 days",
            compression="gz",
            encoding="utf-8",
        )
        cfg.log_dir = str(resolved)
        logger.info("日志文件启用: {}", log_file)

    logger.debug("日志配置完成: console={}, file={}", console_level, file_lvl)
    return cfg
