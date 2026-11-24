"""Money and Exchange Rate.

Money is a `Decimal` that always travels with its currency, so a USD price can never be added
to a TRY amount by accident. Converting to TRY is an explicit step with an `ExchangeRate`;
nothing here rounds (rounding is the display policy in `rounding.py`).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sunquote.domain.errors import CurrencyMismatchError


class Currency(StrEnum):
    TRY = "TRY"
    USD = "USD"
    EUR = "EUR"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> "Money":
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    @classmethod
    def sum(cls, parts: Iterable["Money"], currency: Currency) -> "Money":
        """Total of `parts`, which must all be in `currency`; an empty sum is zero."""
        total = cls(Decimal(0), currency)
        for part in parts:
            total = total + part
        return total

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency is not other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    """How many `quote` units one `base` unit buys, on `rate_date`.

    `overridden` records that the Sales Rep supplied the rate instead of the provider.
    """

    base: Currency
    quote: Currency
    rate: Decimal
    rate_date: date
    overridden: bool = False

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("exchange rate must be positive")
        if self.base is self.quote:
            raise ValueError("the base and quote currencies of an exchange rate must differ")

    def convert(self, money: Money) -> Money:
        """Convert an amount in the base currency into the quote currency."""
        if money.currency is not self.base:
            raise CurrencyMismatchError(self.base, money.currency)
        return Money(money.amount * self.rate, self.quote)


@dataclass(frozen=True, slots=True)
class ExchangeRateOverride:
    """A rate the Sales Rep supplied for the equipment price currency, with the date it applies to.

    It replaces the provider's rate, for example to match a rate agreed with the Customer or
    to reproduce an older Quote.
    """

    rate: Decimal
    rate_date: date

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("exchange rate override: rate must be positive")
