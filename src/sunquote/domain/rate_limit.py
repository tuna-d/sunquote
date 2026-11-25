"""Per-client request limits: a fixed window of calls per client, kept in a `CounterStore`.

The domain decides whether a call fits the limit. Who the client is (an IP address, later an
MCP session) and what a refusal looks like (HTTP 429) are the caller's concern.
"""

import math
from dataclasses import dataclass

from sunquote.domain.ports import Clock, CounterStore


@dataclass(frozen=True)
class RateLimitPolicy:
    """At most `limit` calls per client in each `window_seconds` window.

    `name` separates the counters of different limits, e.g. quote creation and Assistant
    messages.
    """

    name: str
    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("a rate limit must allow at least one call")
        if self.window_seconds < 1:
            raise ValueError("a rate limit window must be at least one second long")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    """Seconds until the window ends and the client may call again (at least 1)."""


class FixedWindowRateLimiter:
    """Counts each client's calls per policy in windows aligned to the Unix epoch.

    A fixed window lets a client use its limit twice around a window boundary. That is fine for
    protecting a free quota from a flood, and it needs one counter per client and window.
    """

    def __init__(self, store: CounterStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def check(self, policy: RateLimitPolicy, client_id: str) -> RateLimitDecision:
        """Count one call of `client_id` against `policy` and say whether it may go ahead.

        Refused calls are counted too, which does not extend the wait: the next window starts
        on its own counter.
        """
        now_seconds = self._clock.now().timestamp()
        window_index = math.floor(now_seconds / policy.window_seconds)
        window_end_seconds = (window_index + 1) * policy.window_seconds
        retry_after_seconds = max(1, math.ceil(window_end_seconds - now_seconds))
        count = await self._store.increment(
            f"ratelimit:{policy.name}:{client_id}:{window_index}",
            # The key is dead once its window is over; a margin covers clock skew between
            # serverless instances.
            ttl_seconds=policy.window_seconds + 60,
        )
        return RateLimitDecision(
            allowed=count <= policy.limit,
            remaining=max(0, policy.limit - count),
            retry_after_seconds=retry_after_seconds,
        )
