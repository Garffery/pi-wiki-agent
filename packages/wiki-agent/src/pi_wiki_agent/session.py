"""Re-export WikiSession from core.agent_session (backward compatibility)."""

from .core.agent_session import SyncResult, WikiSession, WIKI_TOOLS

__all__ = ["SyncResult", "WikiSession", "WIKI_TOOLS"]
