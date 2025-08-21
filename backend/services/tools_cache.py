"""Simple in-memory cache for tools count per service.

This cache is per-process and ephemeral. It is sufficient to avoid repeated
slow probes and to provide fast responses to the UI. We add a short TTL so
that counts are refreshed periodically without being excessively stale.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Optional, Dict


DEFAULT_TTL_SECONDS = 300  # 5 minutes


@dataclass
class ToolsCountEntry:
    count: int
    ts: float


_cache: Dict[int, ToolsCountEntry] = {}


def set_count(service_id: int, count: int) -> None:
    _cache[service_id] = ToolsCountEntry(count=count, ts=time())


def get_count(service_id: int, *, max_age_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[int]:
    entry = _cache.get(service_id)
    if not entry:
        return None
    if time() - entry.ts > max_age_seconds:
        # stale
        return None
    return int(entry.count)


def get_entry(service_id: int) -> Optional[ToolsCountEntry]:
    return _cache.get(service_id)


def clear(service_id: Optional[int] = None) -> None:
    if service_id is None:
        _cache.clear()
    else:
        _cache.pop(service_id, None)

