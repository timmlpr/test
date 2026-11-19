"""Concurrency smoke test against a running API (not part of pytest).

Usage:  python tests/load_smoke.py http://127.0.0.1:8000 50 400
Logs in as the demo user, then fires N requests over C parallel workers against read endpoints and reports
latency percentiles and error rate. Run the backend with RATELIMIT_ENABLED=false for this test only.
"""
from __future__ import annotations

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
conc = int(sys.argv[2]) if len(sys.argv) > 2 else 20
total = int(sys.argv[3]) if len(sys.argv) > 3 else 200

c = httpx.Client(base_url=base, timeout=20)
c.get("/api/health")
csrf = c.cookies.get("fp_csrf")
r = c.post("/api/auth/login", json={"email": "demo@demo.example.com", "password": "TracelowDemo1!"}, headers={"x-csrf-token": csrf})
r.raise_for_status()
cookies = dict(c.cookies)
paths = ["/api/home", "/api/findings", "/api/risk", "/api/timeline", "/api/requests", "/api/health"]


def one(i: int) -> tuple[float, int]:
    t = time.perf_counter()
    with httpx.Client(base_url=base, cookies=cookies, timeout=20) as cl:
        code = cl.get(paths[i % len(paths)]).status_code
    return (time.perf_counter() - t) * 1000, code


t0 = time.perf_counter()
with ThreadPoolExecutor(conc) as ex:
    res = list(ex.map(one, range(total)))
dur = time.perf_counter() - t0
lat = sorted(x for x, _ in res)
errors = sum(1 for _, code in res if code >= 500)
print(f"{total} requests, {conc} workers, {dur:.1f}s → {total / dur:.0f} req/s")
print(f"p50 {statistics.median(lat):.0f} ms · p95 {lat[int(len(lat) * .95)]:.0f} ms · max {lat[-1]:.0f} ms · 5xx {errors}")
sys.exit(1 if errors else 0)
