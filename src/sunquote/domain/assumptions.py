"""Engineering and pricing assumptions the calculation reads. They come from a data file."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.model import RoofType, SubscriberGroup
from sunquote.domain.money import Money


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
class ContractedPower:
    """The Contracted Power a Quote was sized against, and whether the request gave it."""

    kw: Decimal
    given: bool


@dataclass(frozen=True, slots=True)
class EngineeringAssumptions:
    coverage_ratio_by_roof_type: Mapping[RoofType, Decimal]
    system_loss_percent: Decimal
    flat_roof_tilt_deg: Decimal
    dc_ac_ratio_range: DcAcRatioRange
    default_contracted_power_kw_by_subscriber_group: Mapping[SubscriberGroup, Decimal]

    def default_contracted_power_kw(self, subscriber_group: SubscriberGroup) -> Decimal:
        """The Contracted Power assumed when the request gives none."""
        try:
            return self.default_contracted_power_kw_by_subscriber_group[subscriber_group]
        except KeyError:
            raise ValueError(
                f"no default Contracted Power configured for {subscriber_group}"
            ) from None

    def coverage_ratio(self, roof_type: RoofType) -> Decimal:
        try:
            return self.coverage_ratio_by_roof_type[roof_type]
        except KeyError:
            raise ValueError(f"no coverage ratio configured for {roof_type} roofs") from None


@dataclass(frozen=True, slots=True)
class PricingAssumptions:
    """The prices and rates the Installation Cost and Sale Price are built from.

    Every price carries its own currency, declared in the data file; the pricing converts what
    is not TRY. `margin` and `vat_rate` are shares (0.25 is 25%). `validity_period_days` is how
    long a Quote's price holds, counted from the quote date.
    """

    bos_price_per_kwp: Money
    labour_price_per_kwp: Money
    fixed_project_cost: Money
    margin: Decimal
    vat_rate: Decimal
    validity_period_days: int

    def __post_init__(self) -> None:
        if self.validity_period_days <= 0:
            raise ValueError("the validity period must be at least one day")
        if self.margin < 0 or self.vat_rate < 0:
            raise ValueError("margin and VAT rate must not be negative")


@dataclass(frozen=True, slots=True)
class FinancialAssumptions:
    """What the yearly cash flow is built from.

    Both escalation rates are real, inflation-adjusted rates (ADR 0003), so every lifetime
    figure is in today's lira. `inverter_replacement_year` counts from 1 and may lie beyond the
    lifetime, in which case no replacement happens.
    """

    tariff_escalation_rate_real: Decimal
    equipment_escalation_rate_real: Decimal
    lifetime_years: int
    inverter_replacement_year: int

    def __post_init__(self) -> None:
        if self.tariff_escalation_rate_real <= -1 or self.equipment_escalation_rate_real <= -1:
            raise ValueError("escalation rates must be above -100%")
        if self.lifetime_years < 1:
            raise ValueError("the lifetime must be at least one year")
        if self.inverter_replacement_year < 1:
            raise ValueError("the inverter replacement year must be at least 1")
