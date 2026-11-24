"""Quote creation: fetch what the pure entry point needs, then call it."""

from sunquote.domain.assumptions import EngineeringAssumptions
from sunquote.domain.catalog import Catalog
from sunquote.domain.model import QuoteRequest
from sunquote.domain.ports import Clock, SpecificYieldProvider, SpecificYieldQuery
from sunquote.domain.quote import Quote, build_quote


class QuoteService:
    """Orchestrates the ports around `build_quote`. It holds no rules of its own.

    Later tickets add the geocoder, exchange rate provider and repository steps.
    """

    def __init__(
        self,
        *,
        specific_yield_provider: SpecificYieldProvider,
        clock: Clock,
        catalog: Catalog,
        assumptions: EngineeringAssumptions,
    ) -> None:
        self._specific_yield_provider = specific_yield_provider
        self._clock = clock
        self._catalog = catalog
        self._assumptions = assumptions

    async def create_quote(self, request: QuoteRequest) -> Quote:
        roof = request.site.roof
        specific_yield = await self._specific_yield_provider.fetch(
            SpecificYieldQuery(
                coordinates=request.site.coordinates,
                tilt_deg=roof.tilt_deg,
                azimuth_deg=roof.azimuth_deg,
                system_loss_percent=self._assumptions.system_loss_percent,
            )
        )
        return build_quote(
            request=request,
            specific_yield=specific_yield,
            catalog=self._catalog,
            assumptions=self._assumptions,
            quote_date=self._clock.today(),
        )
