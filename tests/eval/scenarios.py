"""Deterministic Quote inputs for the Narrative eval, using synthetic test data."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sunquote.domain.model import Consumption, QuoteRequest, RoofType
from sunquote.domain.money import ExchangeRate
from sunquote.domain.production import SpecificYield
from sunquote.domain.quote import Quote, build_quote, format_quote_number
from sunquote.domain.reference_data import ReferenceData
from tests.factories import (
    MONTHLY_YIELD_KWH_PER_KWP,
    QUOTE_DATE,
    make_exchange_rate,
    make_financial_assumptions,
    make_pricing_assumptions,
    make_reference_data,
    make_request,
    make_specific_yield,
    make_tariff,
)

REFERENCE_DATA = make_reference_data()
NO_EXPORT_DATA = make_reference_data(tariff=make_tariff(export_try_per_kwh="0"))
HIGH_FIXED_COST_DATA = make_reference_data(
    pricing=make_pricing_assumptions(fixed_project_cost_try="700000")
)
SHORT_LIFETIME_NO_EXPORT_DATA = replace(
    NO_EXPORT_DATA, financial=make_financial_assumptions(lifetime_years=9)
)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    request: QuoteRequest
    specific_yield: SpecificYield
    reference_data: ReferenceData
    exchange_rate: ExchangeRate
    quote_date: date
    quote_number: str

    def build(self) -> Quote:
        return build_quote(
            request=self.request,
            specific_yield=self.specific_yield,
            reference_data=self.reference_data,
            exchange_rate=self.exchange_rate,
            quote_date=self.quote_date,
            quote_number=self.quote_number,
        )


def _scenario(
    sequence: int,
    name: str,
    *,
    area_m2: str,
    monthly_kwh: str | None = None,
    monthly_bill_try: str | None = None,
    flat: bool = False,
    azimuth_deg: str = "180",
    contracted_power_kw: str | None = None,
    yield_multiplier: str = "1",
    reference_data: ReferenceData = REFERENCE_DATA,
) -> Scenario:
    request = make_request(
        usable_area_m2=area_m2,
        azimuth_deg=azimuth_deg,
        roof_type=RoofType.FLAT if flat else RoofType.PITCHED,
        contracted_power_kw=contracted_power_kw,
    )
    request = replace(
        request,
        consumption=Consumption(
            monthly_consumption_kwh=None if monthly_kwh is None else Decimal(monthly_kwh),
            monthly_bill_try=None if monthly_bill_try is None else Decimal(monthly_bill_try),
        ),
    )
    azimuth, tilt = request.site.roof.effective_orientation(
        reference_data.engineering.flat_roof_tilt_deg
    )
    monthly = tuple(value * Decimal(yield_multiplier) for value in MONTHLY_YIELD_KWH_PER_KWP)
    specific_yield = make_specific_yield(
        annual=str(sum(monthly)), monthly=monthly, tilt_deg=str(tilt)
    )
    return Scenario(
        name=name,
        request=request,
        specific_yield=replace(
            specific_yield, inputs=replace(specific_yield.inputs, aspect_deg=azimuth - 180)
        ),
        reference_data=reference_data,
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=format_quote_number(QUOTE_DATE.year, sequence),
    )


SCENARIOS = (
    _scenario(1, "south-small-roof", area_m2="13", monthly_kwh="700"),
    _scenario(2, "flat-small-roof", area_m2="24", monthly_kwh="500", flat=True),
    _scenario(3, "south-grid-cap", area_m2="20", monthly_kwh="600", contracted_power_kw="3"),
    _scenario(
        4, "flat-grid-cap", area_m2="60", monthly_kwh="900", flat=True, contracted_power_kw="4"
    ),
    _scenario(5, "south-roof-expansion", area_m2="20", monthly_kwh="330"),
    _scenario(
        6,
        "southwest-roof-expansion",
        area_m2="23",
        monthly_kwh="400",
        azimuth_deg="225",
        yield_multiplier="0.9",
    ),
    _scenario(
        7,
        "east-roof-expansion",
        area_m2="30",
        monthly_kwh="400",
        azimuth_deg="90",
        yield_multiplier="0.8",
    ),
    _scenario(
        8,
        "west-grid-expansion",
        area_m2="40",
        monthly_kwh="400",
        azimuth_deg="270",
        contracted_power_kw="6",
        yield_multiplier="0.9",
    ),
    _scenario(9, "flat-roof-expansion", area_m2="40", monthly_kwh="420", flat=True),
    _scenario(
        10,
        "flat-grid-expansion",
        area_m2="52",
        monthly_kwh="330",
        flat=True,
        contracted_power_kw="3.5",
    ),
    _scenario(
        11,
        "north-single-panel",
        area_m2="3.5",
        monthly_kwh="90",
        azimuth_deg="0",
        yield_multiplier="0.6",
    ),
    _scenario(12, "flat-low-consumption", area_m2="20", monthly_kwh="105", flat=True),
    _scenario(
        13,
        "east-low-consumption",
        area_m2="13",
        monthly_kwh="95",
        azimuth_deg="90",
        yield_multiplier="0.8",
    ),
    _scenario(
        14,
        "northwest-low-yield",
        area_m2="35",
        monthly_kwh="210",
        azimuth_deg="315",
        yield_multiplier="0.6",
    ),
    _scenario(15, "southeast-low-bill", area_m2="20", monthly_bill_try="300", azimuth_deg="135"),
    _scenario(16, "flat-low-bill", area_m2="4.5", monthly_bill_try="345", flat=True),
    _scenario(17, "southwest-high-bill", area_m2="15", monthly_bill_try="1200", azimuth_deg="225"),
    _scenario(
        18,
        "flat-high-fixed-cost",
        area_m2="24",
        monthly_bill_try="2100",
        flat=True,
        yield_multiplier="1.1",
        reference_data=HIGH_FIXED_COST_DATA,
    ),
    _scenario(
        19,
        "west-no-export",
        area_m2="30",
        monthly_bill_try="1750",
        azimuth_deg="270",
        contracted_power_kw="3.5",
        yield_multiplier="0.9",
        reference_data=NO_EXPORT_DATA,
    ),
    _scenario(
        20,
        "flat-no-export",
        area_m2="68",
        monthly_bill_try="2250",
        flat=True,
        yield_multiplier="1.1",
        reference_data=SHORT_LIFETIME_NO_EXPORT_DATA,
    ),
)
