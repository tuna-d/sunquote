"""The fixed-window rate limiter, driven through its public `check`."""

from datetime import UTC, datetime, timedelta

import pytest

from sunquote.domain.rate_limit import FixedWindowRateLimiter, RateLimitPolicy
from tests.fakes import FixedClock, InMemoryCounterStore

pytestmark = pytest.mark.anyio

HOUR = 3600
# Exactly on an hour boundary, so window arithmetic in the tests is easy to follow.
WINDOW_START = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
QUOTES = RateLimitPolicy(name="create-quote", limit=3, window_seconds=HOUR)
ASSISTANT = RateLimitPolicy(name="assistant-message", limit=2, window_seconds=HOUR)


def make_limiter(now: datetime = WINDOW_START) -> tuple[FixedWindowRateLimiter, FixedClock]:
    clock = FixedClock(now=now)
    return FixedWindowRateLimiter(InMemoryCounterStore(clock=clock.now), clock), clock


async def test_calls_up_to_the_limit_are_allowed() -> None:
    limiter, _ = make_limiter()

    decisions = [await limiter.check(QUOTES, "203.0.113.7") for _ in range(3)]

    assert [d.allowed for d in decisions] == [True, True, True]
    assert [d.remaining for d in decisions] == [2, 1, 0]


async def test_the_call_over_the_limit_is_refused_with_the_seconds_until_the_window_ends() -> None:
    limiter, _ = make_limiter(WINDOW_START + timedelta(minutes=20))
    for _ in range(3):
        await limiter.check(QUOTES, "203.0.113.7")

    decision = await limiter.check(QUOTES, "203.0.113.7")

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 40 * 60


async def test_a_refused_call_still_reports_at_least_one_second_to_wait() -> None:
    limiter, _ = make_limiter(WINDOW_START + timedelta(seconds=HOUR - 0.4))
    for _ in range(3):
        await limiter.check(QUOTES, "203.0.113.7")

    decision = await limiter.check(QUOTES, "203.0.113.7")

    assert decision.retry_after_seconds == 1


async def test_counters_are_separate_per_client() -> None:
    limiter, _ = make_limiter()
    for _ in range(3):
        await limiter.check(QUOTES, "203.0.113.7")

    other = await limiter.check(QUOTES, "198.51.100.9")

    assert other.allowed is True


async def test_counters_are_separate_per_policy() -> None:
    limiter, _ = make_limiter()
    for _ in range(3):
        await limiter.check(QUOTES, "203.0.113.7")

    assistant = await limiter.check(ASSISTANT, "203.0.113.7")

    assert assistant.allowed is True
    assert assistant.remaining == 1


async def test_the_window_resets_when_the_next_one_starts() -> None:
    limiter, clock = make_limiter()
    for _ in range(4):
        await limiter.check(QUOTES, "203.0.113.7")

    clock._now = WINDOW_START + timedelta(hours=1)
    decision = await limiter.check(QUOTES, "203.0.113.7")

    assert decision.allowed is True
    assert decision.remaining == 2


async def test_refused_calls_do_not_extend_the_wait() -> None:
    limiter, clock = make_limiter()
    for _ in range(10):
        await limiter.check(QUOTES, "203.0.113.7")
    clock._now = WINDOW_START + timedelta(hours=1, seconds=1)

    assert (await limiter.check(QUOTES, "203.0.113.7")).allowed is True


def test_a_policy_needs_a_positive_limit_and_window() -> None:
    with pytest.raises(ValueError):
        RateLimitPolicy(name="x", limit=0, window_seconds=HOUR)
    with pytest.raises(ValueError):
        RateLimitPolicy(name="x", limit=1, window_seconds=0)
