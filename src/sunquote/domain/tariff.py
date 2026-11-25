"""The residential Retail Tariff: two marginal Tariff Tiers applied month by month, the Export
Price (ADR 0002, ADR 0005).

Savings value Netted Energy through `monthly_cost`. The inverse of `annual_cost` turns a bill
into kWh.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sunquote.domain.errors import CurrencyMismatchError
from sunquote.domain.money import Currency, Money

MONTHS_PER_YEAR = 12

# Days of January..December in a 365-day year. The Tariff Tier thresholds follow it so that the
# twelve of them add up to 365 x the daily allowance (a calendar fact, not tariff data).
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True, slots=True)
class ResidentialTariff:
    """In every month, consumption up to that month's threshold is priced at the low Retail
    Tariff, only the part above it at the high one. A month's threshold is
    `tier_threshold_kwh_per_day` x the month's days in a 365-day year (January 248 kWh,
    February 224 kWh with the 8 kWh/day allowance). Prices are all-in TRY per kWh (taxes and
    fees included) as of `valid_from`; `source` says where the figures come from.
    """

    tier_threshold_kwh_per_day: Decimal
    low_tariff_try_per_kwh: Decimal
    high_tariff_try_per_kwh: Decimal
    export_price_try_per_kwh: Decimal
    valid_from: date
    source: str

    def __post_init__(self) -> None:
        if self.tier_threshold_kwh_per_day <= 0:
            raise ValueError("the daily allowance of the Tariff Tiers must be positive")
        if self.low_tariff_try_per_kwh <= 0 or self.high_tariff_try_per_kwh <= 0:
            raise ValueError("Retail Tariff prices must be positive")
        if self.low_tariff_try_per_kwh > self.high_tariff_try_per_kwh:
            raise ValueError("the low Retail Tariff must not exceed the high one")
        if self.export_price_try_per_kwh < 0:
            raise ValueError("the Export Price must not be negative")

    def monthly_threshold_kwh(self, month: int) -> Decimal:
        """The kWh a month can use at the low tier. `month` counts from 1 (January)."""
        if not 1 <= month <= MONTHS_PER_YEAR:
            raise ValueError("month must be within 1..12")
        return self.tier_threshold_kwh_per_day * _DAYS_IN_MONTH[month - 1]

    def split_month_by_tier(self, month: int, consumption_kwh: Decimal) -> tuple[Decimal, Decimal]:
        """The (low tier, high tier) kWh of one month's consumption."""
        if consumption_kwh < 0:
            raise ValueError("consumption must not be negative")
        low = min(consumption_kwh, self.monthly_threshold_kwh(month))
        return low, consumption_kwh - low

    def monthly_cost(self, month: int, consumption_kwh: Decimal) -> Money:
        """One month's grid cost: min(c, threshold) x low price + max(0, c - threshold) x high."""
        low_kwh, high_kwh = self.split_month_by_tier(month, consumption_kwh)
        cost = low_kwh * self.low_tariff_try_per_kwh + high_kwh * self.high_tariff_try_per_kwh
        return Money(cost, Currency.TRY)

    def split_by_tier(self, annual_consumption_kwh: Decimal) -> tuple[Decimal, Decimal]:
        """The (low tier, high tier) kWh of a flat annual consumption, summed over the months."""
        if annual_consumption_kwh < 0:
            raise ValueError("annual consumption must not be negative")
        monthly_kwh = annual_consumption_kwh / MONTHS_PER_YEAR
        high = Decimal(0)
        for month in range(1, MONTHS_PER_YEAR + 1):
            high += self.split_month_by_tier(month, monthly_kwh)[1]
        return annual_consumption_kwh - high, high

    def annual_cost(self, annual_consumption_kwh: Decimal) -> Money:
        """Annual grid cost of a flat consumption: the sum of its twelve monthly costs."""
        if annual_consumption_kwh < 0:
            raise ValueError("annual consumption must not be negative")
        monthly_kwh = annual_consumption_kwh / MONTHS_PER_YEAR
        total = Decimal(0)
        for month in range(1, MONTHS_PER_YEAR + 1):
            total += self.monthly_cost(month, monthly_kwh).amount
        return Money(total, Currency.TRY)

    def annual_consumption_from_cost(self, annual_cost: Money) -> Decimal:
        """Invert `annual_cost` across the twelve monthly breakpoints.

        The annual cost is piecewise linear in the annual consumption, with a breakpoint at
        12 x each distinct monthly threshold. The inverse interpolates inside the segment that
        holds the cost; above the last breakpoint every month is at the high price.
        """
        if annual_cost.currency is not Currency.TRY:
            raise CurrencyMismatchError(Currency.TRY, annual_cost.currency)
        if annual_cost.amount < 0:
            raise ValueError("annual grid cost must not be negative")
        previous_kwh = Decimal(0)
        previous_cost = Decimal(0)
        for threshold in sorted({self.monthly_threshold_kwh(m) for m in range(1, 13)}):
            kwh = MONTHS_PER_YEAR * threshold
            cost = self.annual_cost(kwh).amount
            if annual_cost.amount <= cost:
                return previous_kwh + (annual_cost.amount - previous_cost) * (
                    kwh - previous_kwh
                ) / (cost - previous_cost)
            previous_kwh, previous_cost = kwh, cost
        return previous_kwh + (annual_cost.amount - previous_cost) / self.high_tariff_try_per_kwh
