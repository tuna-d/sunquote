"""The daily Gemini budget: a global request counter that resets at 00:00 Europe/Istanbul."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from sunquote.domain.errors import GeminiBudgetExhaustedError
from sunquote.domain.gemini_budget import GeminiBudget
from tests.fakes import FixedClock, InMemoryCounterStore

pytestmark = pytest.mark.anyio

# 21:30 UTC is 00:30 the next day in Turkey (UTC+3), so these tests sit right at the boundary.
ISTANBUL_MIDNIGHT = datetime(2026, 11, 24, 21, 0, 0, tzinfo=UTC)


def make_budget(
    limit: int = 3, now: datetime = ISTANBUL_MIDNIGHT + timedelta(hours=10)
) -> tuple[GeminiBudget, FixedClock]:
    clock = FixedClock(now=now)
    return GeminiBudget(InMemoryCounterStore(clock=clock.now), clock, daily_limit=limit), clock


def advance(clock: FixedClock, **delta: float) -> None:
    clock._now += timedelta(**delta)


async def test_requests_up_to_the_limit_are_allowed() -> None:
    budget, _ = make_budget(limit=3)

    for _ in range(3):
        await budget.spend()


async def test_the_request_over_the_limit_is_refused() -> None:
    budget, _ = make_budget(limit=3)
    for _ in range(3):
        await budget.spend()

    with pytest.raises(GeminiBudgetExhaustedError):
        await budget.spend()


async def test_a_spent_budget_stays_spent_for_the_rest_of_the_day() -> None:
    budget, clock = make_budget(limit=1)
    await budget.spend()

    advance(clock, hours=2)

    with pytest.raises(GeminiBudgetExhaustedError):
        await budget.spend()


async def test_the_count_resets_at_midnight_in_istanbul() -> None:
    # 20:59:59 UTC is still the 24th in Istanbul; 21:00:00 UTC is midnight, the 25th.
    budget, clock = make_budget(limit=1, now=ISTANBUL_MIDNIGHT - timedelta(seconds=1))
    await budget.spend()
    with pytest.raises(GeminiBudgetExhaustedError):
        await budget.spend()

    advance(clock, seconds=1)

    await budget.spend()
    with pytest.raises(GeminiBudgetExhaustedError):
        await budget.spend()


async def test_the_day_is_not_the_utc_day() -> None:
    # 22:00 UTC on the 24th is already 01:00 on the 25th in Istanbul: a fresh day, although
    # the UTC date is the same as at the start of the test.
    budget, clock = make_budget(limit=1, now=datetime(2026, 11, 24, 20, 0, tzinfo=UTC))
    await budget.spend()

    advance(clock, hours=2)

    await budget.spend()


async def test_a_refusal_carries_the_limit_for_the_message() -> None:
    budget, _ = make_budget(limit=1)
    await budget.spend()

    with pytest.raises(GeminiBudgetExhaustedError) as caught:
        await budget.spend()

    assert caught.value.daily_limit == 1
    assert "1" in str(caught.value)


async def test_the_limit_must_be_positive() -> None:
    clock = FixedClock()
    with pytest.raises(ValueError):
        GeminiBudget(InMemoryCounterStore(clock=clock.now), clock, daily_limit=0)


class BrokenStore:
    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        raise ConnectionError("redis is down")


async def test_an_unreachable_counter_store_refuses_the_request_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Fail closed (ADR 0007): the free quota must never be exhausted by the demo, and a budget
    # that cannot be checked cannot be known to hold. The Narrative falls back, the Assistant
    # answers its budget-exhausted 503.
    budget = GeminiBudget(BrokenStore(), FixedClock(), daily_limit=5)

    with caplog.at_level(logging.WARNING), pytest.raises(GeminiBudgetExhaustedError) as caught:
        await budget.spend()

    assert caught.value.counter_unavailable is True
    assert "could not be checked" in str(caught.value)
    assert "budget" in caplog.text.lower()


async def test_a_spent_budget_is_not_reported_as_unverifiable() -> None:
    budget, _ = make_budget(limit=1)
    await budget.spend()

    with pytest.raises(GeminiBudgetExhaustedError) as caught:
        await budget.spend()

    assert caught.value.counter_unavailable is False
