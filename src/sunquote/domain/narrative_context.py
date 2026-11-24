"""Builds the anonymised `NarrativeContext` of a Quote: structure only, no figures and no
personal data (ADR 0001)."""

from decimal import ROUND_FLOOR, Decimal

from sunquote.domain.model import RoofType
from sunquote.domain.narrative import (
    NarrativeContext,
    OptionComparison,
    OptionContext,
    Orientation,
    has_comparison,
)
from sunquote.domain.placeholders import available_placeholders
from sunquote.domain.quote import Quote, SystemOption

_COMPASS = (
    Orientation.NORTH,
    Orientation.NORTH_EAST,
    Orientation.EAST,
    Orientation.SOUTH_EAST,
    Orientation.SOUTH,
    Orientation.SOUTH_WEST,
    Orientation.WEST,
    Orientation.NORTH_WEST,
)
_SECTOR_DEG = Decimal(45)


def _orientation(roof_type: RoofType, azimuth_deg: Decimal) -> Orientation:
    """The 45-degree sector the compass bearing falls in; north covers [337.5, 22.5)."""
    if roof_type is RoofType.FLAT:
        return Orientation.FLAT
    shifted = azimuth_deg + _SECTOR_DEG / 2
    sector = int((shifted / _SECTOR_DEG).to_integral_value(rounding=ROUND_FLOOR))
    return _COMPASS[sector % len(_COMPASS)]


def _pays_back_sooner(second: SystemOption, first: SystemOption) -> bool:
    """A payback beyond the lifetime counts as longer than any payback within it."""
    second_payback = second.savings.payback_years
    first_payback = first.savings.payback_years
    if second_payback is None:
        return False
    return first_payback is None or second_payback < first_payback


def build_narrative_context(quote: Quote) -> NarrativeContext:
    options = quote.system_options
    recorded = quote.assumptions
    comparison = None
    if has_comparison(len(options)):
        first, second = options
        comparison = OptionComparison(
            second_option_produces_more=second.annual_production_kwh > first.annual_production_kwh,
            second_option_costs_more=second.price.total.amount > first.price.total.amount,
            second_option_pays_back_sooner=_pays_back_sooner(second, first),
        )
    return NarrativeContext(
        options=tuple(
            OptionContext(
                sizing_strategy=option.strategy,
                binding_limit=option.binding_limit,
                payback_beyond_lifetime=option.savings.payback_beyond_lifetime,
            )
            for option in options
        ),
        roof_type=recorded.roof_type,
        orientation=_orientation(recorded.roof_type, recorded.effective_azimuth_deg),
        annual_consumption_above_tier_threshold=(
            recorded.annual_consumption_kwh > recorded.tariff.tier_threshold_kwh_per_year
        ),
        comparison=comparison,
        available_placeholders=tuple(
            sorted(
                available_placeholders(
                    payback_beyond_lifetime=[
                        option.savings.payback_beyond_lifetime for option in options
                    ]
                )
            )
        ),
    )
