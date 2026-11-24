"""Quote creation: fetch what the pure entry point needs, then call it."""

from datetime import date

from sunquote.domain.assumptions import (
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog
from sunquote.domain.model import QuoteRequest
from sunquote.domain.money import Currency, ExchangeRate, ExchangeRateOverride
from sunquote.domain.ports import (
    Clock,
    ExchangeRateProvider,
    Geocoder,
    QuoteRepository,
    SpecificYieldProvider,
    SpecificYieldQuery,
    StoredQuote,
)
from sunquote.domain.quote import build_quote
from sunquote.domain.tariff import ResidentialTariff

# The currency the Catalog and BOS unit prices are quoted in. The data files enforce it, so the
# Quote needs exactly one rate (this against TRY).
EQUIPMENT_PRICE_CURRENCY = Currency.USD


class QuoteService:
    """Orchestrates the ports around `build_quote`. It holds no rules of its own.

    Resolve the Coordinates, fetch the Specific Yield and Exchange Rate, take the next Quote
    Number, build and save. An upstream outage leaves the sequence untouched. A build that
    fails after the number is issued leaves a gap in the sequence.
    """

    def __init__(
        self,
        *,
        quote_repository: QuoteRepository,
        geocoder: Geocoder,
        specific_yield_provider: SpecificYieldProvider,
        exchange_rate_provider: ExchangeRateProvider,
        clock: Clock,
        catalog: Catalog,
        assumptions: EngineeringAssumptions,
        pricing: PricingAssumptions,
        tariff: ResidentialTariff,
        financial: FinancialAssumptions,
    ) -> None:
        self._quote_repository = quote_repository
        self._geocoder = geocoder
        self._specific_yield_provider = specific_yield_provider
        self._exchange_rate_provider = exchange_rate_provider
        self._clock = clock
        self._catalog = catalog
        self._assumptions = assumptions
        self._pricing = pricing
        self._tariff = tariff
        self._financial = financial

    async def create_quote(
        self,
        request: QuoteRequest,
        *,
        exchange_rate_override: ExchangeRateOverride | None = None,
    ) -> StoredQuote:
        site = request.site
        coordinates = site.coordinates
        geocoding_result = None
        if coordinates is None:
            assert site.address is not None
            geocoding_result = await self._geocoder.geocode(site.address)
            coordinates = geocoding_result.coordinates

        roof = site.roof
        quote_date = self._clock.today()
        azimuth_deg, tilt_deg = roof.effective_orientation(self._assumptions.flat_roof_tilt_deg)
        specific_yield = await self._specific_yield_provider.fetch(
            SpecificYieldQuery(
                coordinates=coordinates,
                tilt_deg=tilt_deg,
                azimuth_deg=azimuth_deg,
                system_loss_percent=self._assumptions.system_loss_percent,
            )
        )
        exchange_rate = await self._exchange_rate(quote_date, exchange_rate_override)
        quote_number = await self._quote_repository.next_quote_number(quote_date.year)
        quote = build_quote(
            request=request,
            specific_yield=specific_yield,
            catalog=self._catalog,
            assumptions=self._assumptions,
            pricing=self._pricing,
            exchange_rate=exchange_rate,
            tariff=self._tariff,
            financial=self._financial,
            quote_date=quote_date,
            quote_number=quote_number,
            geocoding_result=geocoding_result,
        )
        return await self._quote_repository.save(
            quote,
            district=geocoding_result.district if geocoding_result else None,
            province=geocoding_result.province if geocoding_result else None,
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
