"""The daily Gemini budget (ADR 0007): one global request count per day, kept in a `CounterStore`.

Every Gemini request draws one unit, whoever asked for it (a Narrative attempt, its retry, an
Assistant model call). Once the day's units are spent the next request is refused before it
leaves the process, so the free quota is never exceeded. The day runs from 00:00 to 24:00 in
Istanbul and the time comes from the `Clock` port.
"""

import logging
from datetime import timedelta

from sunquote.domain.errors import GeminiBudgetExhaustedError
from sunquote.domain.ports import ISTANBUL, Clock, CounterStore

logger = logging.getLogger(__name__)

_DAY = timedelta(days=1)
# A counter outlives its day by this margin, which covers clock skew between instances.
_TTL_MARGIN_SECONDS = 3600


class GeminiBudget:
    """At most `daily_limit` Gemini requests per Istanbul day, across every serverless instance.

    Refused requests are counted too; that does not matter, because the next day starts on its
    own counter.
    """

    def __init__(self, store: CounterStore, clock: Clock, *, daily_limit: int) -> None:
        if daily_limit < 1:
            raise ValueError("the daily Gemini budget must allow at least one request")
        self._store = store
        self._clock = clock
        self._daily_limit = daily_limit

    @property
    def daily_limit(self) -> int:
        return self._daily_limit

    async def spend(self) -> None:
        """Draw one request from today's budget, or raise `GeminiBudgetExhaustedError`.

        When the counters cannot be reached the request goes through and the failure is logged:
        abuse protection must not take the demo down with it, and Gemini's own quota still
        answers with an error the callers already handle.
        """
        now = self._clock.now().astimezone(ISTANBUL)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_left = (day_start + _DAY - now).total_seconds()
        try:
            count = await self._store.increment(
                f"gemini-budget:{now.date().isoformat()}",
                ttl_seconds=int(seconds_left) + _TTL_MARGIN_SECONDS,
            )
        except Exception:
            logger.warning("Gemini budget check failed; letting the request through", exc_info=True)
            return
        if count > self._daily_limit:
            raise GeminiBudgetExhaustedError(self._daily_limit)
