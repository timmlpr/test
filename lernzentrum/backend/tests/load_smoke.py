"""Load smoke test against a running stack (not part of pytest). Usage:
    python tests/load_smoke.py http://localhost:3000 [concurrency] [requests]
Logs in as the demo user and fires concurrent requests at the hot endpoints (home, search, ask, events)."""
from __future__ import annotations

import asyncio
import statistics
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
CONC = int(sys.argv[2]) if len(sys.argv) > 2 else 20
TOTAL = int(sys.argv[3]) if len(sys.argv) > 3 else 400


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"email": "demo@lernzentrum.app", "password": "Lernzentrum2026"})
        r.raise_for_status()
        csrf = c.cookies.get("lz_csrf")
        endpoints = [("GET", "/api/home", None), ("GET", "/api/search?q=Verj%C3%A4hrung%20Kaufpreis", None),
                     ("POST", "/api/ask", {"question": "Wie lange müssen Buchungsbelege aufbewahrt werden?"}),
                     ("GET", "/api/recordings/1/events?after=0", None), ("GET", "/api/modules/1/dashboard", None)]
        lat: dict[str, list[float]] = {p: [] for _, p, _ in endpoints}
        errors = 0
        sem = asyncio.Semaphore(CONC)

        async def one(i: int) -> None:
            nonlocal errors
            m, p, body = endpoints[i % len(endpoints)]
            async with sem:
                t = time.perf_counter()
                resp = await c.request(m, p, json=body, headers={"x-csrf-token": csrf or ""})
                lat[p].append((time.perf_counter() - t) * 1000)
                if resp.status_code >= 400:
                    errors += 1

        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(TOTAL)))
        dur = time.perf_counter() - t0
        print(f"{TOTAL} requests, concurrency {CONC}: {TOTAL / dur:.1f} req/s, errors {errors}")
        for p, v in lat.items():
            v.sort()
            print(f"  {p[:45]:45s} p50 {statistics.median(v):6.0f} ms  p95 {v[int(len(v) * 0.95) - 1]:6.0f} ms")
        sys.exit(1 if errors else 0)


asyncio.run(main())
