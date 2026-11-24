"""Inverter selection and pricing of one System Option, all in TRY."""

from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.assumptions import DcAcRatioRange, PricingAssumptions
from sunquote.domain.catalog import Inverter, Panel
from sunquote.domain.errors import NoCompatibleInverterError
from sunquote.domain.money import Currency, ExchangeRate, Money


def to_try(money: Money, rate: ExchangeRate) -> Money:
    """TRY amounts pass through; anything else is converted with `rate`."""
    if money.currency is Currency.TRY:
        return money
    return rate.convert(money)


def dc_ac_ratio(capacity_kwp: Decimal, inverter: Inverter) -> Decimal:
    return capacity_kwp / inverter.ac_power_kw


def select_inverter(
    *,
    inverters: tuple[Inverter, ...],
    capacity_kwp: Decimal,
    ratio_range: DcAcRatioRange,
    rate: ExchangeRate,
) -> Inverter:
    """The cheapest inverter in TRY whose DC/AC Ratio is within the range.

    Equal prices go to the smaller AC power, then to the id, so the choice is deterministic.
    Raises `NoCompatibleInverterError` when none qualifies.
    """
    compatible = [
        inverter
        for inverter in inverters
        if ratio_range.contains(dc_ac_ratio(capacity_kwp, inverter))
    ]
    if not compatible:
        raise NoCompatibleInverterError(str(capacity_kwp))
    return min(
        compatible,
        key=lambda inverter: (
            to_try(inverter.unit_price, rate).amount,
            inverter.ac_power_kw,
            inverter.inverter_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class SystemPrice:
    """What a System Option costs and sells for. Every amount is unrounded TRY."""

    installation_cost: Money
    sale_price: Money
    vat: Money
    total: Money


def price_system(
    *,
    panel: Panel,
    panel_count: int,
    inverter: Inverter,
    capacity_kwp: Decimal,
    pricing: PricingAssumptions,
    rate: ExchangeRate,
) -> SystemPrice:
    """Installation Cost -> Sale Price (x (1 + Margin)) -> VAT -> total.

    Installation Cost = (panels + inverter + BOS) converted to TRY + labour + fixed project cost.
    """
    equipment = [
        panel.unit_price * panel_count,
        inverter.unit_price,
        pricing.bos_price_per_kwp * capacity_kwp,
    ]
    installation_cost = Money.sum(
        [
            *(to_try(part, rate) for part in equipment),
            pricing.labour_price_per_kwp * capacity_kwp,
            pricing.fixed_project_cost,
        ],
        Currency.TRY,
    )
    sale_price = installation_cost * (1 + pricing.margin)
    vat = sale_price * pricing.vat_rate
    return SystemPrice(
        installation_cost=installation_cost,
        sale_price=sale_price,
        vat=vat,
        total=sale_price + vat,
    )
