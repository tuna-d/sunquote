"""The rate limiter, with a fake clock and sleep so no test waits for real time."""

import asyncio

import pytest

from sunquote.adapters.rate_limiter import RateLimiter

pytestmark = pytest.mark.anyio


class FakeTime:
    """A clock that moves when the test moves it or when a sleep ends, like real time: a sleep
    started at `t` for `s` seconds ends with the clock at `t + s` (never going backwards), so
    sleepers that overlap do not add up. `sleeps` records every wait.
    `first_sleep_wakes_early_by` makes the first sleep return that many seconds before it was
    due, as `asyncio.sleep` can on Windows."""

    def __init__(self, *, first_sleep_wakes_early_by: float = 0.0) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []
        self._early_by = first_sleep_wakes_early_by

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        started = self.now
        self.sleeps.append(seconds)
        due = started + seconds - self._early_by
        self._early_by = 0.0
        await asyncio.sleep(0)  # let the other callers run while this one sleeps
        self.now = max(self.now, due)


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
    fake = FakeTime()
    limiter = make_limiter(fake, interval=2.0)
    woke_at: list[float] = []

    async def request() -> None:
        await limiter.wait()
        woke_at.append(fake.now)

    # All three arrive at the same instant and each takes the next free slot.
    await asyncio.gather(request(), request(), request())

    assert sorted(woke_at) == [100.0, 102.0, 104.0]


async def test_a_wake_up_before_the_slot_sleeps_again_until_it() -> None:
    # asyncio.sleep can return up to one clock tick early (Windows); the call must not go
    # out before its slot, so the limiter checks the clock and sleeps the rest.
    fake = FakeTime(first_sleep_wakes_early_by=0.125)
    limiter = make_limiter(fake)
    await limiter.wait()
    fake.now += 0.25
    slot = 101.0

    await limiter.wait()

    assert fake.sleeps == [0.75, 0.125]
    assert fake.now >= slot


async def test_limiters_do_not_share_state() -> None:
    fake = FakeTime()

    await make_limiter(fake).wait()
    await make_limiter(fake).wait()

    assert fake.sleeps == []


def test_the_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="interval"):
        RateLimiter(0)
