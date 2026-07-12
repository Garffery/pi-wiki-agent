"""Context compression for wiki sessions — mirrors pi_coding_agent/core/compaction/compaction.py"""

from __future__ import annotations

from typing import Any


async def compact_context(
    session: Any,
    messages: list[dict],
    reserve_tokens: int = 16384,
) -> list[dict]:
    """Compact the agent context, preserving wiki-specific system instructions."""
    from pi_coding_agent.core.compaction.compaction import compact_context as _base_compact
    return await _base_compact(session, messages, reserve_tokens)


def should_compact(messages: list[dict], threshold: int = 100000) -> bool:
    """Check if compaction is needed based on message token count."""
    total = sum(len(str(m.get("content", ""))) for m in messages)
    return total > threshold
