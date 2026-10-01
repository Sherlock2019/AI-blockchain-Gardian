"""Fixed-window rate limiter, per caller.

In-process only: adequate for one instance, wrong for several. A deployment
behind a load balancer would enforce this at the gateway or in Redis.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.errors import RateLimitedError


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, caller: str) -> None:
        if self._limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            window = self._calls[caller]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self._limit:
                raise RateLimitedError("Too many requests. Try again shortly.")
            window.append(now)
