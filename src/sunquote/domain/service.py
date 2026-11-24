"""Quote creation: fetch what the pure entry point needs, then call it."""

from datetime import date

from sunquote.domain.assumptions import EngineeringAssumptions, PricingAssumptions
from sunquote.domain.catalog import Catalog
from sunquote.domain.model import QuoteRequest
from sunquote.domain.money import Currency, ExchangeRate, ExchangeRateOverride
from sunquote.domain.ports import (
    Clock,
    ExchangeRateProvider,
    SpecificYieldProvider,
    SpecificYieldQuery,
)
from sunquote.domain.quote import Quote, build_quote

# The currency the Catalog and BOS unit prices are quoted in. The data files enforce it, so the
# Quote needs exactly one rate (this against TRY).
EQUIPMENT_PRICE_CURRENCY = Currency.USD


class QuoteService:
    """Orchestrates the ports around `build_quote`. It holds no rules of its own.

    Later tickets add the geocoder and repository steps.
    """

    def __init__(
        self,
        *,
        specific_yield_provider: SpecificYieldProvider,
        exchange_rate_provider: ExchangeRateProvider,
        clock: Clock,
        catalog: Catalog,
        assumptions: EngineeringAssumptions,
        pricing: PricingAssumptions,
    ) -> None:
        self._specific_yield_provider = specific_yield_provider
        self._exchange_rate_provider = exchange_rate_provider
        self._clock = clock
        self._catalog = catalog
        self._assumptions = assumptions
        self._pricing = pricing

    async def create_quote(
        self,
        request: QuoteRequest,
        *,
        exchange_rate_override: ExchangeRateOverride | None = None,
    ) -> Quote:
        roof = request.site.roof
        quote_date = self._clock.today()
        specific_yield = await self._specific_yield_provider.fetch(
            SpecificYieldQuery(
                coordinates=request.site.coordinates,
                tilt_deg=roof.tilt_deg,
                azimuth_deg=roof.azimuth_deg,
                system_loss_percent=self._assumptions.system_loss_percent,
            )
        )
        exchange_rate = await self._exchange_rate(quote_date, exchange_rate_override)
        return build_quote(
            request=request,
            specific_yield=specific_yield,
            catalog=self._catalog,
            assumptions=self._assumptions,
            pricing=self._pricing,
            exchange_rate=exchange_rate,
            quote_date=quote_date,
        )

    async def _exchange_rate(
        self, quote_date: date, override: ExchangeRateOverride | None
    ) -> ExchangeRate:
        """The override when given (the provider is not called), else the provider's rate."""
        if override is not None:
            return ExchangeRate(
                base=EQUIPMENT_PRICE_CURRENCY,
                quote=Currency.TRY,
                rate=override.rate,
                rate_date=override.rate_date,
                overridden=True,
            )
        return await self._exchange_rate_provider.fetch(EQUIPMENT_PRICE_CURRENCY, quote_date)
