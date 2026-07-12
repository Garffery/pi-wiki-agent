"""Compaction utility functions for wiki-agent."""

from __future__ import annotations

from typing import Any


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (4 chars ~= 1 token)."""
    return len(text) // 4


def summarize_messages(messages: list[dict], max_chars: int = 2000) -> str:
    """Create a brief summary of conversation messages."""
    parts: list[str] = []
    total = 0
    for m in reversed(messages):
        content = str(m.get("content", ""))[:200]
        if content.strip():
            parts.append(f"[{m.get('role', '?')}]: {content}")
            total += len(content)
            if total > max_chars:
                break
    return "\n".join(reversed(parts))
