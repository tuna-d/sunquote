"""The rate limiter, with a fake clock and sleep so no test waits for real time."""

import asyncio

import pytest

from sunquote.adapters.rate_limiter import RateLimiter

pytestmark = pytest.mark.anyio


class FakeTime:
    """A clock that only moves when the test moves it, or, with `advance_on_sleep`, when
    something sleeps. `sleeps` records every wait."""

    def __init__(self, *, advance_on_sleep: bool = True) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []
        self._advance_on_sleep = advance_on_sleep

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self._advance_on_sleep:
            self.now += seconds
        await asyncio.sleep(0)


def make_limiter(fake: FakeTime, interval: float = 1.0) -> RateLimiter:
    return RateLimiter(interval, clock=fake.clock, sleep=fake.sleep)


async def test_the_first_request_does_not_wait() -> None:
    fake = FakeTime()

    await make_limiter(fake).wait()

    assert fake.sleeps == []


async def test_a_request_right_after_another_waits_for_the_rest_of_the_interval() -> None:
    fake = FakeTime()
    limiter = make_limiter(fake)

    await limiter.wait()
    fake.now += 0.25  # time passes outside the limiter
    await limiter.wait()

    assert fake.sleeps == [pytest.approx(0.75)]


async def test_a_request_after_the_interval_has_passed_does_not_wait() -> None:
    fake = FakeTime()
    limiter = make_limiter(fake)

    await limiter.wait()
    fake.now += 1.0
    await limiter.wait()

    assert fake.sleeps == []


async def test_concurrent_requests_are_spaced_one_interval_apart() -> None:
    fake = FakeTime(advance_on_sleep=False)  # all three arrive at the same instant
    limiter = make_limiter(fake, interval=2.0)

    await asyncio.gather(limiter.wait(), limiter.wait(), limiter.wait())

    # Each takes the next free slot: now, now + 2 s and now + 4 s.
    assert fake.sleeps == [2.0, 4.0]


async def test_limiters_do_not_share_state() -> None:
    fake = FakeTime()

    await make_limiter(fake).wait()
    await make_limiter(fake).wait()

    assert fake.sleeps == []


def test_the_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="interval"):
        RateLimiter(0)
