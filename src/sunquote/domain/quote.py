"""The domain entry point: a pure function that builds a Quote from fully resolved inputs."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sunquote.domain.assumptions import (
    ContractedPower,
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
from sunquote.domain.sizing import (
    BindingLimit,
    Sizing,
    SizingStrategy,
    contracted_power_cap_panels,
    roof_capacity_panels,
    size_consumption_matched,
    size_roof_max,
)


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
    contracted_power: ContractedPower
    pricing: PricingAssumptions
    exchange_rate: ExchangeRate


@dataclass(frozen=True, slots=True)
class Quote:
    customer: Customer
    quote_date: date
    system_options: tuple[SystemOption, ...]
    assumptions: QuoteAssumptions


def _build_option(
    *,
    strategy: SizingStrategy,
    sizing: Sizing,
    panel: Panel,
    specific_yield: SpecificYield,
    catalog: Catalog,
    assumptions: EngineeringAssumptions,
    pricing: PricingAssumptions,
    exchange_rate: ExchangeRate,
    contracted_power: ContractedPower,
) -> SystemOption:
    capacity_kwp = sizing.panel_count * panel.capacity_kwp
    inverter = select_inverter(
        inverters=catalog.inverters,
        capacity_kwp=capacity_kwp,
        ratio_range=assumptions.dc_ac_ratio_range,
        max_ac_power_kw=contracted_power.kw,
        rate=exchange_rate,
    )
    return SystemOption(
        strategy=strategy,
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


def build_quote(
    *,
    request: QuoteRequest,
    specific_yield: SpecificYield,
    catalog: Catalog,
    assumptions: EngineeringAssumptions,
    pricing: PricingAssumptions,
    exchange_rate: ExchangeRate,
    quote_date: date,
) -> Quote:
    """Build the Quote. No clock, file system or network: everything arrives as an argument.

    The Quote holds the Consumption-Matched System Option, followed by the Roof-Max one when
    its panel count differs. Both respect the Roof and the Contracted Power.

    Raises `NoViableSystemError` when the Roof or the Contracted Power allows no panel and
    `NoCompatibleInverterError` when no inverter keeps the DC/AC Ratio within the configured
    range with an AC power of at most the Contracted Power.
    """
    roof = request.site.roof
    panel = catalog.default_panel
    coverage_ratio = assumptions.coverage_ratio(roof.roof_type)
    azimuth_deg, tilt_deg = roof.effective_orientation(assumptions.flat_roof_tilt_deg)
    contracted_power = _contracted_power(request, assumptions)

    roof_panels = roof_capacity_panels(roof.usable_area_m2, coverage_ratio, panel)
    cap_panels = contracted_power_cap_panels(
        contracted_power.kw, assumptions.dc_ac_ratio_range.maximum, panel
    )
    consumption_matched = size_consumption_matched(
        monthly_consumption_kwh=request.consumption.monthly_consumption_kwh,
        annual_kwh_per_kwp=specific_yield.annual_kwh_per_kwp,
        roof_panels=roof_panels,
        contracted_power_cap_panels=cap_panels,
        panel=panel,
    )
    sizings = [(SizingStrategy.CONSUMPTION_MATCHED, consumption_matched)]
    roof_max = size_roof_max(roof_panels=roof_panels, contracted_power_cap_panels=cap_panels)
    if roof_max.panel_count != consumption_matched.panel_count:
        sizings.append((SizingStrategy.ROOF_MAX, roof_max))

    options = tuple(
        _build_option(
            strategy=strategy,
            sizing=sizing,
            panel=panel,
            specific_yield=specific_yield,
            catalog=catalog,
            assumptions=assumptions,
            pricing=pricing,
            exchange_rate=exchange_rate,
            contracted_power=contracted_power,
        )
        for strategy, sizing in sizings
    )
    return Quote(
        customer=request.customer,
        quote_date=quote_date,
        system_options=options,
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
            contracted_power=contracted_power,
            pricing=pricing,
            exchange_rate=exchange_rate,
        ),
    )


def _contracted_power(
    request: QuoteRequest, assumptions: EngineeringAssumptions
) -> ContractedPower:
    """The request's Contracted Power, or the Subscriber Group's default when it gives none."""
    if request.contracted_power_kw is not None:
        return ContractedPower(kw=request.contracted_power_kw, given=True)
    return ContractedPower(
        kw=assumptions.default_contracted_power_kw(request.subscriber_group), given=False
    )
