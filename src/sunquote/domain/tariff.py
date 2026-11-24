"""The residential Retail Tariff: two marginal Tariff Tiers, the Export Price and the
Self-Consumption Ratio (ADR 0002).

`annual_cost` is the one tier cost function. Savings value self-consumed energy through it, and
a later ticket inverts it to turn a Monthly Bill into kWh.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sunquote.domain.money import Currency, Money


@dataclass(frozen=True, slots=True)
class ResidentialTariff:
    """Annual consumption up to `tier_threshold_kwh_per_year` is priced at the low Retail
    Tariff, only the part above it at the high one. Prices are all-in TRY per kWh (taxes and
    fees included) as of `valid_from`; `source` says where the figures come from.
    """

    tier_threshold_kwh_per_year: Decimal
    low_tariff_try_per_kwh: Decimal
    high_tariff_try_per_kwh: Decimal
    export_price_try_per_kwh: Decimal
    self_consumption_ratio: Decimal
    valid_from: date
    source: str

    def __post_init__(self) -> None:
        if self.tier_threshold_kwh_per_year <= 0:
            raise ValueError("the Tariff Tier threshold must be positive")
        if self.low_tariff_try_per_kwh <= 0 or self.high_tariff_try_per_kwh <= 0:
            raise ValueError("Retail Tariff prices must be positive")
        if self.low_tariff_try_per_kwh > self.high_tariff_try_per_kwh:
            raise ValueError("the low Retail Tariff must not exceed the high one")
        if self.export_price_try_per_kwh < 0:
            raise ValueError("the Export Price must not be negative")
        if not 0 <= self.self_consumption_ratio <= 1:
            raise ValueError("the Self-Consumption Ratio must be within [0, 1]")

    def split_by_tier(self, annual_consumption_kwh: Decimal) -> tuple[Decimal, Decimal]:
        """The (low tier, high tier) kWh of an annual consumption."""
        if annual_consumption_kwh < 0:
            raise ValueError("annual consumption must not be negative")
        low = min(annual_consumption_kwh, self.tier_threshold_kwh_per_year)
        return low, annual_consumption_kwh - low

    def annual_cost(self, annual_consumption_kwh: Decimal) -> Money:
        """Annual grid cost: min(C, threshold) x low price + max(0, C - threshold) x high price."""
        low_kwh, high_kwh = self.split_by_tier(annual_consumption_kwh)
        cost = low_kwh * self.low_tariff_try_per_kwh + high_kwh * self.high_tariff_try_per_kwh
        return Money(cost, Currency.TRY)
