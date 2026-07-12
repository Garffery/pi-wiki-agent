"""Centralized logging for wiki-agent.

Usage::

    from pi_wiki_agent.logging import logger

    logger.info("sync complete, {} pages modified", len(pages))
    logger.debug("filtered files: {}", files)

To enable file logging, call ``configure()`` once at startup::

    from pi_wiki_agent.logging import configure
    configure(project_root="/path/to/project")
"""

from .config import logger, configure, LoggerConfig

__all__ = ["logger", "configure", "LoggerConfig"]
