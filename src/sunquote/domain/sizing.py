"""Sizing: how many panels a System Option gets and what limited it."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from sunquote.domain.catalog import Panel
from sunquote.domain.errors import NoViableSystemError


class SizingStrategy(StrEnum):
    CONSUMPTION_MATCHED = "consumption_matched"


class BindingLimit(StrEnum):
    ROOF = "roof"
    CONSUMPTION_TARGET = "consumption_target"


@dataclass(frozen=True, slots=True)
class Sizing:
    panel_count: int
    binding_limit: BindingLimit


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def roof_capacity_panels(usable_area_m2: Decimal, coverage_ratio: Decimal, panel: Panel) -> int:
    """Whole panels that fit: floor(usable area x Coverage Ratio / panel area)."""
    return _floor(usable_area_m2 * coverage_ratio / panel.area_m2)


def consumption_target_kwp(
    monthly_consumption_kwh: Decimal, annual_kwh_per_kwp: Decimal
) -> Decimal:
    """The size whose annual production equals annual consumption: 12 x monthly / yield."""
    return 12 * monthly_consumption_kwh / annual_kwh_per_kwp


def size_consumption_matched(
    *,
    monthly_consumption_kwh: Decimal,
    annual_kwh_per_kwp: Decimal,
    usable_area_m2: Decimal,
    coverage_ratio: Decimal,
    panel: Panel,
) -> Sizing:
    """Panels = max(1, floor(target kWp / panel kWp)), capped by what the Roof fits.

    A tie between the two counts is attributed to the Roof.
    """
    roof_panels = roof_capacity_panels(usable_area_m2, coverage_ratio, panel)
    if roof_panels < 1:
        raise NoViableSystemError

    target_kwp = consumption_target_kwp(monthly_consumption_kwh, annual_kwh_per_kwp)
    target_panels = max(1, _floor(target_kwp / panel.capacity_kwp))

    if roof_panels <= target_panels:
        return Sizing(panel_count=roof_panels, binding_limit=BindingLimit.ROOF)
    return Sizing(panel_count=target_panels, binding_limit=BindingLimit.CONSUMPTION_TARGET)
