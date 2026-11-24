"""Engineering and pricing assumptions the calculation reads. They come from a data file."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.model import RoofType
from sunquote.domain.money import Currency, Money


@dataclass(frozen=True, slots=True)
class DcAcRatioRange:
    """The allowed DC/AC Ratio, both limits inclusive."""

    minimum: Decimal
    maximum: Decimal

    def __post_init__(self) -> None:
        if not 0 < self.minimum <= self.maximum:
            raise ValueError("the DC/AC Ratio range needs 0 < minimum <= maximum")

    def contains(self, ratio: Decimal) -> bool:
        return self.minimum <= ratio <= self.maximum


@dataclass(frozen=True, slots=True)
class EngineeringAssumptions:
    coverage_ratio_by_roof_type: Mapping[RoofType, Decimal]
    system_loss_percent: Decimal
    flat_roof_tilt_deg: Decimal
    dc_ac_ratio_range: DcAcRatioRange

    def coverage_ratio(self, roof_type: RoofType) -> Decimal:
        try:
            return self.coverage_ratio_by_roof_type[roof_type]
        except KeyError:
            raise ValueError(f"no coverage ratio configured for {roof_type} roofs") from None


@dataclass(frozen=True, slots=True)
class PricingAssumptions:
    """The prices and rates the Installation Cost and Sale Price are built from.

    The BOS (mounting and cabling) price may be in a foreign currency; labour and the fixed
    project cost are TRY. `margin` and `vat_rate` are shares (0.25 is 25%).
    """

    bos_price_per_kwp: Money
    labour_price_per_kwp: Money
    fixed_project_cost: Money
    margin: Decimal
    vat_rate: Decimal

    def __post_init__(self) -> None:
        if self.labour_price_per_kwp.currency is not Currency.TRY:
            raise ValueError("the labour price per kWp must be in TRY")
        if self.fixed_project_cost.currency is not Currency.TRY:
            raise ValueError("the fixed project cost must be in TRY")
        if self.margin < 0 or self.vat_rate < 0:
            raise ValueError("margin and VAT rate must not be negative")
