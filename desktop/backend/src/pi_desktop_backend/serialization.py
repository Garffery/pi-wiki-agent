"""Convert AgentEvent objects to JSON-serializable dicts for WebSocket."""

from __future__ import annotations

import json
from typing import Any

from pi_agent.types import AgentEvent


def serialize_agent_event(event: AgentEvent) -> dict[str, Any]:
    """Convert any AgentEvent to a JSON-serializable dict."""
    if isinstance(event, dict):
        return event

    try:
        base = event.model_dump(mode="json", exclude_none=False)
    except Exception:
        return {"type": "unknown", "raw": str(event)}

    event_type = base.pop("type", "unknown")
    return {"type": event_type, **base}


def safe_json_serialize(obj: Any) -> str:
    """JSON serialize with a fallback for non-serializable objects."""
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return json.dumps({"error": "serialization_failed"})
