"""Branch navigation summary for wiki-agent sessions."""

from __future__ import annotations

from typing import Any


async def summarize_branch(
    session_manager: Any,
    leaf_id: str,
    target_id: str,
    model: Any | None = None,
    api_key: str | None = None,
) -> Any:
    """Summarize a branch navigation in the session tree."""
    from pi_coding_agent.core.compaction.branch_summarization import summarize_branch as _base_summarize
    return await _base_summarize(session_manager, leaf_id, target_id, model, api_key)
