"""The domain entry point: a pure function that builds a Quote from fully resolved inputs."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sunquote.domain.assumptions import EngineeringAssumptions
from sunquote.domain.catalog import Catalog, Panel
from sunquote.domain.model import Customer, QuoteRequest
from sunquote.domain.production import (
    SpecificYield,
    SpecificYieldInputs,
    annual_production_kwh,
    monthly_production_kwh,
)
from sunquote.domain.sizing import BindingLimit, SizingStrategy, size_consumption_matched


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


@dataclass(frozen=True, slots=True)
class QuoteAssumptions:
    """Everything the Quote was calculated with, so it can be reproduced later.

    Later tickets add the Exchange Rate, Tariff, unit prices, Margin, VAT and the rest.
    """

    submitted_request: QuoteRequest
    pvgis_inputs: SpecificYieldInputs
    coverage_ratio: Decimal
    default_panel: Panel


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
    quote_date: date,
) -> Quote:
    """Build the Quote. No clock, file system or network: everything arrives as an argument.

    Raises `NoViableSystemError` when the Roof fits no panel.
    """
    roof = request.site.roof
    panel = catalog.default_panel
    coverage_ratio = assumptions.coverage_ratio(roof.roof_type)

    sizing = size_consumption_matched(
        monthly_consumption_kwh=request.consumption.monthly_consumption_kwh,
        annual_kwh_per_kwp=specific_yield.annual_kwh_per_kwp,
        usable_area_m2=roof.usable_area_m2,
        coverage_ratio=coverage_ratio,
        panel=panel,
    )
    capacity_kwp = sizing.panel_count * panel.capacity_kwp

    option = SystemOption(
        strategy=SizingStrategy.CONSUMPTION_MATCHED,
        panel=panel,
        panel_count=sizing.panel_count,
        capacity_kwp=capacity_kwp,
        binding_limit=sizing.binding_limit,
        annual_production_kwh=annual_production_kwh(capacity_kwp, specific_yield),
        monthly_production_kwh=monthly_production_kwh(capacity_kwp, specific_yield),
    )
    return Quote(
        customer=request.customer,
        quote_date=quote_date,
        system_options=(option,),
        assumptions=QuoteAssumptions(
            submitted_request=request,
            pvgis_inputs=specific_yield.inputs,
            coverage_ratio=coverage_ratio,
            default_panel=panel,
        ),
    )
