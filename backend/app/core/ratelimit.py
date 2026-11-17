"""In-memory sliding-window rate limiter (per IP + route). Single-process deployment."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.errors import ApiError

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()
ENABLED = True


def hit(key: str, limit: int, window_s: int) -> None:
    if not ENABLED:
        return
    t = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] < t - window_s:
            q.popleft()
        if len(q) >= limit:
            raise ApiError(429, "rate_limited", retry_after=int(window_s - (t - q[0])) + 1)
        q.append(t)


def reset() -> None:
    with _lock:
        _hits.clear()
