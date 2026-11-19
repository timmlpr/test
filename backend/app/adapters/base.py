"""Source-adapter plugin framework.

Every adapter declares its source, terms of use, allowed data types and rate limits. The registry
refuses to enable adapters whose `permitted` flag is False (no documented permission). Calls go
through `Adapter.http()` which applies quota, per-second throttle, retries with backoff and a
clean `SourceUnavailable` error instead of crashes.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from threading import Lock

import httpx

USER_AGENT = "TracelowBot/1.0 (+privacy self-check; contact via site imprint)"


class SourceUnavailable(Exception):
    def __init__(self, source: str, reason: str):
        super().__init__(f"{source}: {reason}")
        self.source, self.reason = source, reason


class QuotaExceeded(SourceUnavailable):
    pass


class MissingKey(SourceUnavailable):
    pass


@dataclass
class AdapterMeta:
    name: str
    label: str
    modules: list[str]
    terms_url: str
    data_types: list[str]
    requires_key: bool = False
    paid: bool = False
    permitted: bool = True
    default_enabled: bool = True
    rate_per_day: int = 1000
    min_interval_s: float = 0.0
    key_env: str | None = None
    signup_url: str | None = None
    notes: str = ""
    verified_on: str = "2026-11-17"
    extra: dict = field(default_factory=dict)


class Adapter:
    meta: AdapterMeta
    _last_call: float = 0.0
    _lock = Lock()

    # --- key handling -------------------------------------------------------------------------
    def key(self) -> str | None:
        from app.adapters.registry import stored_key

        k = stored_key(self.meta.name)
        if k:
            return k
        return os.environ.get(self.meta.key_env or "", "") or None

    def enabled(self) -> bool:
        from app.adapters.registry import is_enabled

        return is_enabled(self)

    def require_key(self) -> str:
        k = self.key()
        if not k:
            raise MissingKey(self.meta.name, "missing_key")
        return k

    # --- HTTP with quota + throttle + retry -----------------------------------------------------
    def http(self, method: str, url: str, *, retries: int = 2, timeout: float = 12.0, **kw) -> httpx.Response:
        from app.adapters.quota import quota

        if not self.meta.permitted:
            raise SourceUnavailable(self.meta.name, "not_permitted")
        quota.take(self.meta.name, self.meta.rate_per_day)
        headers = {"User-Agent": USER_AGENT, **kw.pop("headers", {})}
        delay = 0.6
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            with self._lock:
                wait = self.meta.min_interval_s - (time.monotonic() - type(self)._last_call)
                if wait > 0:
                    time.sleep(wait)
                type(self)._last_call = time.monotonic()
            try:
                r = httpx.request(method, url, headers=headers, timeout=timeout, follow_redirects=True, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if r.status_code in (401, 403):
                    quota.error(self.meta.name)
                    raise SourceUnavailable(self.meta.name, f"auth_{r.status_code}")
                return r
            except httpx.HTTPError as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
        quota.error(self.meta.name)
        raise SourceUnavailable(self.meta.name, f"unreachable:{type(last_exc).__name__}")

    def test(self) -> str:
        """Lightweight connectivity check for the admin 'Manage keys' page."""
        return "ok"
