"""A small rate limiter for outbound calls to a service with a request-rate policy."""

import asyncio
from collections.abc import Awaitable, Callable
from threading import Lock
from time import monotonic


class RateLimiter:
    """Spaces calls at least `min_interval_seconds` apart.

    `wait()` hands out the next free time slot and sleeps until it, so concurrent callers queue
    up one interval apart. The slot is taken under a thread lock, so one instance can be shared
    by every client in the process, also across event loops. The clock and the sleep are
    injectable so tests need not wait for real time. A sleep that wakes early is slept off again.
    """

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if min_interval_seconds <= 0:
            raise ValueError("the rate limiter interval must be positive")
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = Lock()
        self._next_slot = float("-inf")

    async def wait(self) -> None:
        """Return when this caller may make its request."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval_seconds
        # `asyncio.sleep` can return a clock tick early (on Windows), which would let the request
        # out just before its slot: sleep again until the clock has really reached it.
        while (remaining := slot - self._clock()) > 0:
            await self._sleep(remaining)
