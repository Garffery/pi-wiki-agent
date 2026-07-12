"""Async sleep with cancellation support."""

from __future__ import annotations

import asyncio


async def sleep(seconds: float, cancel_event: asyncio.Event | None = None) -> bool:
    """Sleep for seconds, or until cancel_event is set. Returns True if slept fully."""
    if cancel_event is None:
        await asyncio.sleep(seconds)
        return True
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
        return False
    except asyncio.TimeoutError:
        return True
