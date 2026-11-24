"""The domain entry point: a pure function that builds a Quote from fully resolved inputs."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sunquote.domain.assumptions import (
    DcAcRatioRange,
    EngineeringAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog, Inverter, Panel
from sunquote.domain.model import Customer, QuoteRequest, RoofType
from sunquote.domain.money import ExchangeRate
from sunquote.domain.pricing import SystemPrice, dc_ac_ratio, price_system, select_inverter
from sunquote.domain.production import (
    SpecificYield,
    SpecificYieldInputs,
    annual_production_kwh,
    monthly_production_kwh,
)
from sunquote.domain.sizing import BindingLimit, SizingStrategy, size_consumption_matched

QUOTE_NUMBER_SEQUENCE_DIGITS = 6


def format_quote_number(year: int, sequence: int) -> str:
    """`SQ-<year>-<6-digit sequence>`, for example `SQ-2026-000123`."""
    if sequence < 1 or sequence >= 10**QUOTE_NUMBER_SEQUENCE_DIGITS:
        raise ValueError(f"quote sequence out of range: {sequence}")
    return f"SQ-{year}-{sequence:0{QUOTE_NUMBER_SEQUENCE_DIGITS}d}"


@dataclass(frozen=True, slots=True)
class SystemOption:
    """One candidate system. Every figure is unrounded; rounding happens only on display."""

    strategy: SizingStrategy
    panel: Panel
    panel_count: int
    capacity_kwp: Decimal
    binding_limit: BindingLimit
    annual_production_kwh: Decimal
    monthly_production_kwh: tuple[Decimal, ...]
    inverter: Inverter
    dc_ac_ratio: Decimal
    price: SystemPrice


@dataclass(frozen=True, slots=True)
class QuoteAssumptions:
    """Everything the Quote was calculated with, so it can be reproduced later.

    `inverters` is the whole list the inverter choice was made from. Later tickets add the
    Tariff and the financial assumptions.
    """

    submitted_request: QuoteRequest
    pvgis_inputs: SpecificYieldInputs
    roof_type: RoofType
    effective_azimuth_deg: Decimal
    effective_tilt_deg: Decimal
    coverage_ratio: Decimal
    default_panel: Panel
    inverters: tuple[Inverter, ...]
    dc_ac_ratio_range: DcAcRatioRange
    pricing: PricingAssumptions
    exchange_rate: ExchangeRate


@dataclass(frozen=True, slots=True)
class Quote:
    """A priced offer. It is never changed after creation: re-quoting makes a new Quote.

    `quote_number` is the readable identifier the repository issued (`SQ-2026-000123`);
    `valid_until` is the quote date plus the Validity Period.
    """

    quote_number: str
    customer: Customer
    quote_date: date
    valid_until: date
    system_options: tuple[SystemOption, ...]
    assumptions: QuoteAssumptions


def build_quote(
    *,
    request: QuoteRequest,
    specific_yield: SpecificYield,
    catalog: Catalog,
    assumptions: EngineeringAssumptions,
    pricing: PricingAssumptions,
    exchange_rate: ExchangeRate,
    quote_date: date,
    quote_number: str,
) -> Quote:
    """Build the Quote. No clock, file system or network: everything arrives as an argument.

    Raises `NoViableSystemError` when the Roof fits no panel and `NoCompatibleInverterError`
    when no inverter keeps the DC/AC Ratio within the configured range.
    """
    roof = request.site.roof
    panel = catalog.default_panel
    coverage_ratio = assumptions.coverage_ratio(roof.roof_type)
    azimuth_deg, tilt_deg = roof.effective_orientation(assumptions.flat_roof_tilt_deg)

    sizing = size_consumption_matched(
        monthly_consumption_kwh=request.consumption.monthly_consumption_kwh,
        annual_kwh_per_kwp=specific_yield.annual_kwh_per_kwp,
        usable_area_m2=roof.usable_area_m2,
        coverage_ratio=coverage_ratio,
        panel=panel,
    )
    capacity_kwp = sizing.panel_count * panel.capacity_kwp
    inverter = select_inverter(
        inverters=catalog.inverters,
        capacity_kwp=capacity_kwp,
        ratio_range=assumptions.dc_ac_ratio_range,
        rate=exchange_rate,
    )

    option = SystemOption(
        strategy=SizingStrategy.CONSUMPTION_MATCHED,
        panel=panel,
        panel_count=sizing.panel_count,
        capacity_kwp=capacity_kwp,
        binding_limit=sizing.binding_limit,
        annual_production_kwh=annual_production_kwh(capacity_kwp, specific_yield),
        monthly_production_kwh=monthly_production_kwh(capacity_kwp, specific_yield),
        inverter=inverter,
        dc_ac_ratio=dc_ac_ratio(capacity_kwp, inverter),
        price=price_system(
            panel=panel,
            panel_count=sizing.panel_count,
            inverter=inverter,
            capacity_kwp=capacity_kwp,
            pricing=pricing,
            rate=exchange_rate,
        ),
    )
    return Quote(
        quote_number=quote_number,
        customer=request.customer,
        quote_date=quote_date,
        valid_until=quote_date + timedelta(days=pricing.validity_period_days),
        system_options=(option,),
        assumptions=QuoteAssumptions(
            submitted_request=request,
            pvgis_inputs=specific_yield.inputs,
            roof_type=roof.roof_type,
            effective_azimuth_deg=azimuth_deg,
            effective_tilt_deg=tilt_deg,
            coverage_ratio=coverage_ratio,
            default_panel=panel,
            inverters=catalog.inverters,
            dc_ac_ratio_range=assumptions.dc_ac_ratio_range,
            pricing=pricing,
            exchange_rate=exchange_rate,
        ),
    )
