"""Sizing: how many panels a System Option gets and what limited it."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum

from sunquote.domain.catalog import Panel
from sunquote.domain.errors import NoViableSystemError


class SizingStrategy(StrEnum):
    CONSUMPTION_MATCHED = "consumption_matched"
    ROOF_MAX = "roof_max"


class BindingLimit(StrEnum):
    ROOF = "roof"
    CONSUMPTION_TARGET = "consumption_target"
    CONTRACTED_POWER = "contracted_power"


# When several limits give the same panel count, the first in this order is the Binding Limit.
_TIE_ORDER = (BindingLimit.CONTRACTED_POWER, BindingLimit.ROOF, BindingLimit.CONSUMPTION_TARGET)

_NO_PANEL_REASON = {
    BindingLimit.CONTRACTED_POWER: "the Contracted Power allows no panel",
    BindingLimit.ROOF: "the usable roof area fits no panel",
}


@dataclass(frozen=True, slots=True)
class Sizing:
    panel_count: int
    binding_limit: BindingLimit


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def roof_capacity_panels(usable_area_m2: Decimal, coverage_ratio: Decimal, panel: Panel) -> int:
    """Whole panels that fit: floor(usable area x Coverage Ratio / panel area)."""
    return _floor(usable_area_m2 * coverage_ratio / panel.area_m2)


def contracted_power_cap_panels(
    contracted_power_kw: Decimal, max_dc_ac_ratio: Decimal, panel: Panel
) -> int:
    """Whole panels the grid connection allows: floor(Contracted Power x max DC/AC / panel kWp)."""
    return _floor(contracted_power_kw * max_dc_ac_ratio / panel.capacity_kwp)


def consumption_target_kwp(
    monthly_consumption_kwh: Decimal, annual_kwh_per_kwp: Decimal
) -> Decimal:
    """The size whose annual production equals annual consumption: 12 x monthly / yield."""
    return 12 * monthly_consumption_kwh / annual_kwh_per_kwp


def consumption_target_panels(
    monthly_consumption_kwh: Decimal, annual_kwh_per_kwp: Decimal, panel: Panel
) -> int:
    """max(1, floor(target kWp / panel kWp)): never below one panel."""
    target_kwp = consumption_target_kwp(monthly_consumption_kwh, annual_kwh_per_kwp)
    return max(1, _floor(target_kwp / panel.capacity_kwp))


def _bind(panel_counts_by_limit: dict[BindingLimit, int]) -> Sizing:
    """The smallest count wins; a tie goes to the limit that comes first in the tie order.

    Raises `NoViableSystemError` when that count is zero.
    """
    panel_count = min(panel_counts_by_limit.values())
    binding_limit = next(
        limit for limit in _TIE_ORDER if panel_counts_by_limit.get(limit) == panel_count
    )
    if panel_count < 1:
        raise NoViableSystemError(_NO_PANEL_REASON[binding_limit])
    return Sizing(panel_count=panel_count, binding_limit=binding_limit)


def size_consumption_matched(
    *,
    monthly_consumption_kwh: Decimal,
    annual_kwh_per_kwp: Decimal,
    roof_panels: int,
    contracted_power_cap_panels: int,
    panel: Panel,
) -> Sizing:
    """The consumption target (at least one panel), capped by the Roof and Contracted Power."""
    return _bind(
        {
            BindingLimit.CONSUMPTION_TARGET: consumption_target_panels(
                monthly_consumption_kwh, annual_kwh_per_kwp, panel
            ),
            BindingLimit.ROOF: roof_panels,
            BindingLimit.CONTRACTED_POWER: contracted_power_cap_panels,
        }
    )


def size_roof_max(*, roof_panels: int, contracted_power_cap_panels: int) -> Sizing:
    """As many panels as the Roof fits, capped by Contracted Power."""
    return _bind(
        {
            BindingLimit.ROOF: roof_panels,
            BindingLimit.CONTRACTED_POWER: contracted_power_cap_panels,
        }
    )
