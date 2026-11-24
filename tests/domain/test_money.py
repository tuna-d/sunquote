"""Money and Exchange Rate: the value objects every price is built from."""

from datetime import date
from decimal import Decimal

import pytest

from sunquote.domain.errors import CurrencyMismatchError
from sunquote.domain.money import Currency, ExchangeRate, Money

RATE_DATE = date(2026, 11, 23)


def usd_try(rate: str = "50") -> ExchangeRate:
    return ExchangeRate(
        base=Currency.USD, quote=Currency.TRY, rate=Decimal(rate), rate_date=RATE_DATE
    )


def test_money_of_the_same_currency_adds_and_scales() -> None:
    total = Money(Decimal("10.50"), Currency.USD) + Money(Decimal("4.25"), Currency.USD)

    assert total == Money(Decimal("14.75"), Currency.USD)
    assert total * 2 == Money(Decimal("29.50"), Currency.USD)
    assert Decimal("0.5") * total == Money(Decimal("7.375"), Currency.USD)


def test_money_does_not_mix_currencies() -> None:
    with pytest.raises(CurrencyMismatchError, match=r"USD.*TRY"):
        Money(Decimal(1), Currency.USD) + Money(Decimal(1), Currency.TRY)


def test_money_of_the_same_currency_subtracts_and_can_go_negative() -> None:
    ten = Money(Decimal("10.50"), Currency.TRY)
    four = Money(Decimal("4.25"), Currency.TRY)

    assert ten - four == Money(Decimal("6.25"), Currency.TRY)
    assert four - ten == Money(Decimal("-6.25"), Currency.TRY)


def test_money_does_not_subtract_across_currencies() -> None:
    with pytest.raises(CurrencyMismatchError, match=r"USD.*TRY"):
        Money(Decimal(1), Currency.USD) - Money(Decimal(1), Currency.TRY)


def test_money_sums_with_the_zero_of_its_currency() -> None:
    parts = [Money(Decimal(2), Currency.TRY), Money(Decimal(3), Currency.TRY)]

    assert Money.sum(parts, Currency.TRY) == Money(Decimal(5), Currency.TRY)
    assert Money.sum([], Currency.USD) == Money(Decimal(0), Currency.USD)
    with pytest.raises(CurrencyMismatchError):
        Money.sum(parts, Currency.USD)


def test_conversion_to_try_is_an_explicit_step_with_the_rate() -> None:
    converted = usd_try("50.4936").convert(Money(Decimal("100"), Currency.USD))

    assert converted == Money(Decimal("5049.36"), Currency.TRY)


def test_a_rate_converts_only_its_own_base_currency() -> None:
    with pytest.raises(CurrencyMismatchError):
        usd_try().convert(Money(Decimal(1), Currency.EUR))


@pytest.mark.parametrize("rate", ["0", "-1"])
def test_an_exchange_rate_must_be_positive(rate: str) -> None:
    with pytest.raises(ValueError, match="rate"):
        usd_try(rate)


def test_an_exchange_rate_between_the_same_currency_is_refused() -> None:
    with pytest.raises(ValueError, match="differ"):
        ExchangeRate(base=Currency.TRY, quote=Currency.TRY, rate=Decimal(1), rate_date=RATE_DATE)
