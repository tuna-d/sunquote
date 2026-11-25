"""Quote creation: fetch what the pure entry point needs, then call it."""

import asyncio
import logging
from dataclasses import replace
from datetime import date, datetime

from sunquote.domain.errors import GeminiBudgetExhaustedError, NarrativeUnavailableError
from sunquote.domain.model import QuoteRequest
from sunquote.domain.money import Currency, ExchangeRate, ExchangeRateOverride
from sunquote.domain.narrative import (
    NO_NARRATIVE,
    FallbackReason,
    NarrativeDraft,
    NarrativeRecord,
    NarrativeSource,
    Violation,
    validate_narrative,
)
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.ports import (
    Clock,
    ExchangeRateProvider,
    Geocoder,
    NarrativeWriter,
    QuoteRepository,
    SpecificYieldProvider,
    SpecificYieldQuery,
    StoredQuote,
)
from sunquote.domain.quote import Quote, build_quote, format_quote_number
from sunquote.domain.reference_data import ReferenceData

logger = logging.getLogger(__name__)

DEFAULT_NARRATIVE_BUDGET_SECONDS = 15.0


async def generate_narrative(
    quote: Quote,
    *,
    writer: NarrativeWriter | None,
    generated_at: datetime,
    budget_seconds: float,
) -> NarrativeRecord:
    """Return a Quote's validated Narrative, or a fallback when generation fails."""
    if writer is None:
        return replace(NO_NARRATIVE, generated_at=generated_at)
    try:
        async with asyncio.timeout(budget_seconds):
            draft = await _validated_draft(writer, quote)
    except GeminiBudgetExhaustedError as error:
        logger.warning("Narrative not written, using the fixed text: %s", error)
        return replace(
            NO_NARRATIVE, generated_at=generated_at, fallback_reason=FallbackReason.BUDGET_SPENT
        )
    except (NarrativeUnavailableError, TimeoutError) as error:
        logger.warning("Narrative unavailable, using the fixed text: %s", error)
        draft = None
    except Exception as error:
        # An unexpected failure: log the type only, since an arbitrary message could carry
        # a secret (a key echoed in a client error, say).
        logger.warning(
            "Narrative writer failed unexpectedly (%s), using the fixed text",
            type(error).__name__,
        )
        draft = None
    if draft is None:
        return replace(NO_NARRATIVE, generated_at=generated_at)
    return NarrativeRecord(
        source=NarrativeSource.LLM,
        draft=draft,
        model=writer.model_name,
        generated_at=generated_at,
    )


async def _validated_draft(writer: NarrativeWriter, quote: Quote) -> NarrativeDraft | None:
    """A draft that passes the validator, asking once more after a rejection; else None."""
    context = build_narrative_context(quote)
    violations: tuple[Violation, ...] = ()
    for _ in range(2):
        draft = await writer.write(context, previous_violations=violations)
        violations = validate_narrative(draft, context)
        if not violations:
            return draft
        logger.info("Narrative draft rejected: %s", [v.kind.value for v in violations])
    return None


class QuoteService:
    """Orchestrates the ports around `build_quote`. It holds no rules of its own.

    Resolve the Coordinates, fetch the Specific Yield and Exchange Rate, check that a system can
    be built, take the next Quote Number, build the final Quote and save. An upstream outage or
    a build that fails with a domain error leaves the sequence untouched: the number is taken
    only once the Quote is known to build. (A failure of the save itself can still leave a gap.)

    The Narrative step runs after the Quote is built and before it is saved: the writer drafts,
    the validator checks, one retry gets the violations, and both attempts share
    `narrative_budget_seconds`. Anything else (no writer, a second rejection, an error, a
    timeout, any other exception from the writer) records a `fallback` Narrative. The step never
    makes Quote creation fail.
    """

    def __init__(
        self,
        *,
        quote_repository: QuoteRepository,
        geocoder: Geocoder,
        specific_yield_provider: SpecificYieldProvider,
        exchange_rate_provider: ExchangeRateProvider,
        clock: Clock,
        reference_data: ReferenceData,
        narrative_writer: NarrativeWriter | None = None,
        narrative_budget_seconds: float = DEFAULT_NARRATIVE_BUDGET_SECONDS,
    ) -> None:
        self._quote_repository = quote_repository
        self._geocoder = geocoder
        self._specific_yield_provider = specific_yield_provider
        self._exchange_rate_provider = exchange_rate_provider
        self._clock = clock
        self._reference_data = reference_data
        self._narrative_writer = narrative_writer
        self._narrative_budget_seconds = narrative_budget_seconds

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

        engineering = self._reference_data.engineering
        quote_date = self._clock.today()
        azimuth_deg, tilt_deg = site.roof.effective_orientation(engineering.flat_roof_tilt_deg)
        specific_yield = await self._specific_yield_provider.fetch(
            SpecificYieldQuery(
                coordinates=coordinates,
                tilt_deg=tilt_deg,
                azimuth_deg=azimuth_deg,
                system_loss_percent=engineering.system_loss_percent,
            )
        )
        exchange_rate = await self._exchange_rate(quote_date, exchange_rate_override)

        def build(quote_number: str) -> Quote:
            return build_quote(
                request=request,
                specific_yield=specific_yield,
                reference_data=self._reference_data,
                exchange_rate=exchange_rate,
                quote_date=quote_date,
                quote_number=quote_number,
                geocoding_result=geocoding_result,
            )

        # Validate with a provisional number first: a domain error must not use up a real one.
        build(format_quote_number(quote_date.year, 1))
        quote = build(await self._quote_repository.next_quote_number(quote_date.year))
        narrative = await generate_narrative(
            quote,
            writer=self._narrative_writer,
            generated_at=self._clock.now(),
            budget_seconds=self._narrative_budget_seconds,
        )
        quote = replace(quote, narrative=narrative)
        return await self._quote_repository.save(
            quote,
            district=geocoding_result.district if geocoding_result else None,
            province=geocoding_result.province if geocoding_result else None,
        )

    async def _exchange_rate(
        self, quote_date: date, override: ExchangeRateOverride | None
    ) -> ExchangeRate:
        """The override when given (the provider is not called), else the provider's rate.

        The rate is for the currency the data files price the equipment in.
        """
        currency = self._reference_data.exchange_rate_currency
        if override is not None:
            return ExchangeRate(
                base=currency,
                quote=Currency.TRY,
                rate=override.rate,
                rate_date=override.rate_date,
                overridden=True,
            )
        return await self._exchange_rate_provider.fetch(currency, quote_date)
