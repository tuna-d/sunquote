"""In-memory stand-ins for the domain's ports. Later specs add the geocoder, exchange rate
provider and repository fakes here, so every test layer shares them."""

from datetime import date

from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.ports import SpecificYieldQuery
from sunquote.domain.production import SpecificYield
from tests.factories import QUOTE_DATE, make_specific_yield


class FixedClock:
    def __init__(self, today: date = QUOTE_DATE) -> None:
        self._today = today

    def today(self) -> date:
        return self._today


class FakeSpecificYieldProvider:
    """Returns a canned Specific Yield and records every query it receives.

    Pass `error` to simulate an outage.
    """

    def __init__(
        self,
        specific_yield: SpecificYield | None = None,
        error: UpstreamUnavailableError | None = None,
    ) -> None:
        self.specific_yield = specific_yield or make_specific_yield()
        self.error = error
        self.queries: list[SpecificYieldQuery] = []

    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.specific_yield
