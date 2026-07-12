"""Central timing instrumentation for wiki-agent profiling. Enable with PI_TIMING=1."""

from __future__ import annotations

import os
import sys
import time as _time

_ENABLED = os.environ.get("PI_TIMING") == "1"
_timings: list[dict[str, object]] = []
_last_time: float = _time.time() * 1000


def time(label: str) -> None:
    global _last_time
    if not _ENABLED:
        return
    now = _time.time() * 1000
    _timings.append({"label": label, "ms": int(now - _last_time)})
    _last_time = now


def print_timings() -> None:
    if not _ENABLED or not _timings:
        return
    print("\n--- Wiki Agent Timings ---", file=sys.stderr)
    for t in _timings:
        print(f"  {t['label']}: {t['ms']}ms", file=sys.stderr)
    total = sum(t["ms"] for t in _timings)  # type: ignore[misc]
    print(f"  TOTAL: {total}ms", file=sys.stderr)


def reset_timings() -> None:
    global _last_time
    _timings.clear()
    _last_time = _time.time() * 1000
