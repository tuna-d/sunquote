"""The rounding policy: the one place that decides how displayed values are rounded.

Calculation runs on unrounded `Decimal`s. These functions are applied only at the edge, to
the figures a Sales Rep or Customer reads. Every rule rounds half-up (away from zero on a
tie), the way a Customer would round by hand.
"""

from decimal import ROUND_HALF_UP, Decimal

_WHOLE = Decimal("1")
_TWO_DECIMALS = Decimal("0.01")
_ONE_DECIMAL = Decimal("0.1")


def _half_up(value: Decimal, exponent: Decimal) -> Decimal:
    return value.quantize(exponent, rounding=ROUND_HALF_UP)


def round_try(amount_try: Decimal) -> int:
    """TRY amounts are shown in whole lira."""
    return int(_half_up(amount_try, _WHOLE))


def round_capacity_kwp(capacity_kwp: Decimal) -> Decimal:
    """`capacity_kwp` is shown with 2 decimals."""
    return _half_up(capacity_kwp, _TWO_DECIMALS)


def round_kwh(energy_kwh: Decimal) -> int:
    """Energy is shown in whole kWh."""
    return int(_half_up(energy_kwh, _WHOLE))


def round_payback_years(payback_years: Decimal) -> Decimal:
    """The Payback Period is shown with 1 decimal."""
    return _half_up(payback_years, _ONE_DECIMAL)


def round_try_per_kwh(price_try_per_kwh: Decimal) -> Decimal:
    """Tariff and Export Prices are shown with 2 decimals."""
    return _half_up(price_try_per_kwh, _TWO_DECIMALS)


def round_share(share: Decimal) -> Decimal:
    """A share kept as a ratio (0.853) for the API is given with 3 decimals."""
    return _half_up(share, Decimal("0.001"))


def round_exchange_rate(rate: Decimal) -> Decimal:
    """An Exchange Rate is shown with 4 decimals, the precision TCMB publishes."""
    return _half_up(rate, Decimal("0.0001"))


def round_percent(share: Decimal) -> Decimal:
    """A share (0.25) is shown as a percentage (25.0) with 1 decimal."""
    return _half_up(share * 100, _ONE_DECIMAL)
