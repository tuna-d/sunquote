"""The domain entry point: a pure function that builds a Quote from fully resolved inputs."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sunquote.domain.assumptions import (
    ContractedPower,
    DcAcRatioRange,
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Inverter, Panel
from sunquote.domain.model import Customer, GeocodingResult, QuoteRequest, RoofType
from sunquote.domain.money import Currency, ExchangeRate, Money
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
from sunquote.domain.reference_data import ReferenceData
from sunquote.domain.savings import SavingsAnalysis, analyze_savings
from sunquote.domain.sizing import (
    BindingLimit,
    Sizing,
    SizingStrategy,
    contracted_power_cap_panels,
    roof_capacity_panels,
    size_consumption_matched,
    size_roof_max,
)
from sunquote.domain.tariff import ResidentialTariff

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
    contracted_power: ContractedPower
    pricing: PricingAssumptions
    exchange_rate: ExchangeRate
    annual_consumption_kwh: Decimal
    low_tier_consumption_kwh: Decimal
    high_tier_consumption_kwh: Decimal
    tariff: ResidentialTariff
    financial: FinancialAssumptions
    derived_monthly_consumption_kwh: Decimal | None = None
    geocoding_result: GeocodingResult | None = None

    @property
    def consumption_derived_from_bill(self) -> bool:
        return self.derived_monthly_consumption_kwh is not None


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


def _build_option(
    *,
    strategy: SizingStrategy,
    sizing: Sizing,
    panel: Panel,
    specific_yield: SpecificYield,
    reference_data: ReferenceData,
    exchange_rate: ExchangeRate,
    contracted_power: ContractedPower,
    annual_consumption_kwh: Decimal,
) -> SystemOption:
    pricing = reference_data.pricing
    capacity_kwp = sizing.panel_count * panel.capacity_kwp
    inverter = select_inverter(
        inverters=reference_data.catalog.inverters,
        capacity_kwp=capacity_kwp,
        ratio_range=reference_data.engineering.dc_ac_ratio_range,
        max_ac_power_kw=contracted_power.kw,
        rate=exchange_rate,
    )
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
        tariff=reference_data.tariff,
        financial=reference_data.financial,
        inverter_price_incl_vat=to_try(inverter.unit_price, exchange_rate) * (1 + pricing.vat_rate),
        total_price_incl_vat=price.total,
    )
    return SystemOption(
        strategy=strategy,
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


def build_quote(
    *,
    request: QuoteRequest,
    specific_yield: SpecificYield,
    reference_data: ReferenceData,
    exchange_rate: ExchangeRate,
    quote_date: date,
    quote_number: str,
    geocoding_result: GeocodingResult | None = None,
) -> Quote:
    """Build the Quote. No clock, file system or network: everything arrives as an argument.

    The Quote holds the Consumption-Matched System Option, followed by the Roof-Max one when
    its panel count differs. Both respect the Roof and the Contracted Power.

    Raises `NoViableSystemError` when the Roof or the Contracted Power allows no panel and
    `NoCompatibleInverterError` when no inverter keeps the DC/AC Ratio within the configured
    range with an AC power of at most the Contracted Power.
    """
    catalog = reference_data.catalog
    assumptions = reference_data.engineering
    pricing = reference_data.pricing
    tariff = reference_data.tariff
    financial = reference_data.financial
    roof = request.site.roof
    panel = catalog.default_panel
    coverage_ratio = assumptions.coverage_ratio(roof.roof_type)
    azimuth_deg, tilt_deg = roof.effective_orientation(assumptions.flat_roof_tilt_deg)
    contracted_power = _contracted_power(request, assumptions)
    monthly_consumption_kwh = request.consumption.monthly_consumption_kwh
    derived_monthly_consumption_kwh = None
    if monthly_consumption_kwh is None:
        monthly_bill_try = request.consumption.monthly_bill_try
        assert monthly_bill_try is not None
        annual_consumption_kwh = tariff.annual_consumption_from_cost(
            12 * Money(monthly_bill_try, Currency.TRY)
        )
        monthly_consumption_kwh = annual_consumption_kwh / 12
        derived_monthly_consumption_kwh = monthly_consumption_kwh
    else:
        annual_consumption_kwh = 12 * monthly_consumption_kwh
    low_tier_kwh, high_tier_kwh = tariff.split_by_tier(annual_consumption_kwh)

    roof_panels = roof_capacity_panels(roof.usable_area_m2, coverage_ratio, panel)
    cap_panels = contracted_power_cap_panels(
        contracted_power.kw, assumptions.dc_ac_ratio_range.maximum, panel
    )
    consumption_matched = size_consumption_matched(
        monthly_consumption_kwh=monthly_consumption_kwh,
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
            reference_data=reference_data,
            exchange_rate=exchange_rate,
            contracted_power=contracted_power,
            annual_consumption_kwh=annual_consumption_kwh,
        )
        for strategy, sizing in sizings
    )
    return Quote(
        quote_number=quote_number,
        customer=request.customer,
        quote_date=quote_date,
        valid_until=quote_date + timedelta(days=pricing.validity_period_days),
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
            annual_consumption_kwh=annual_consumption_kwh,
            low_tier_consumption_kwh=low_tier_kwh,
            high_tier_consumption_kwh=high_tier_kwh,
            tariff=tariff,
            financial=financial,
            derived_monthly_consumption_kwh=derived_monthly_consumption_kwh,
            geocoding_result=geocoding_result,
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
