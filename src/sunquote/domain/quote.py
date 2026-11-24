"""The domain entry point: a pure function that builds a Quote from fully resolved inputs."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sunquote.domain.assumptions import (
    DcAcRatioRange,
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog, Inverter, Panel
from sunquote.domain.model import Customer, QuoteRequest, RoofType
from sunquote.domain.money import ExchangeRate
from sunquote.domain.pricing import (
    SystemPrice,
    dc_ac_ratio,
    price_system,
    select_inverter,
    to_try,
)
from sunquote.domain.production import (
    SpecificYield,
    SpecificYieldInputs,
    annual_production_kwh,
    monthly_production_kwh,
)
from sunquote.domain.savings import SavingsAnalysis, analyze_savings
from sunquote.domain.sizing import BindingLimit, SizingStrategy, size_consumption_matched
from sunquote.domain.tariff import ResidentialTariff


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
    savings: SavingsAnalysis


@dataclass(frozen=True, slots=True)
class QuoteAssumptions:
    """Everything the Quote was calculated with, so it can be reproduced later.

    `inverters` is the whole list the inverter choice was made from. The annual consumption and
    its split across the Tariff Tiers (ADR 0002) are recorded, not one chosen tier. The
    financial assumptions hold real escalation rates (ADR 0003).
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
    annual_consumption_kwh: Decimal
    low_tier_consumption_kwh: Decimal
    high_tier_consumption_kwh: Decimal
    tariff: ResidentialTariff
    financial: FinancialAssumptions


@dataclass(frozen=True, slots=True)
class Quote:
    customer: Customer
    quote_date: date
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
    tariff: ResidentialTariff,
    financial: FinancialAssumptions,
    quote_date: date,
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

    annual_consumption_kwh = 12 * request.consumption.monthly_consumption_kwh
    low_tier_kwh, high_tier_kwh = tariff.split_by_tier(annual_consumption_kwh)
    year1_production_kwh = annual_production_kwh(capacity_kwp, specific_yield)
    price = price_system(
        panel=panel,
        panel_count=sizing.panel_count,
        inverter=inverter,
        capacity_kwp=capacity_kwp,
        pricing=pricing,
        rate=exchange_rate,
    )
    savings = analyze_savings(
        year1_production_kwh=year1_production_kwh,
        annual_consumption_kwh=annual_consumption_kwh,
        degradation_rate_per_year=panel.degradation_rate_per_year,
        tariff=tariff,
        financial=financial,
        inverter_price_incl_vat=to_try(inverter.unit_price, exchange_rate) * (1 + pricing.vat_rate),
        total_price_incl_vat=price.total,
    )

    option = SystemOption(
        strategy=SizingStrategy.CONSUMPTION_MATCHED,
        panel=panel,
        panel_count=sizing.panel_count,
        capacity_kwp=capacity_kwp,
        binding_limit=sizing.binding_limit,
        annual_production_kwh=year1_production_kwh,
        monthly_production_kwh=monthly_production_kwh(capacity_kwp, specific_yield),
        inverter=inverter,
        dc_ac_ratio=dc_ac_ratio(capacity_kwp, inverter),
        price=price,
        savings=savings,
    )
    return Quote(
        customer=request.customer,
        quote_date=quote_date,
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
            annual_consumption_kwh=annual_consumption_kwh,
            low_tier_consumption_kwh=low_tier_kwh,
            high_tier_consumption_kwh=high_tier_kwh,
            tariff=tariff,
            financial=financial,
        ),
    )
