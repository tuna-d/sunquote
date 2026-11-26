"""Annual Savings under Monthly Netting, the yearly cash flow and the Payback Period of one
System Option (ADR 0005), and its Net Present Value and Internal Rate of Return (ADR 0006).

Everything is TRY in today's lira: the escalation rates are real (ADR 0003), the Discount Rate
is real too, and the Payback Period is undiscounted. Nothing here rounds; rounding is the
display policy.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.assumptions import FinancialAssumptions
from sunquote.domain.errors import CurrencyMismatchError
from sunquote.domain.money import Currency, Money
from sunquote.domain.tariff import MONTHS_PER_YEAR, ResidentialTariff

_ZERO_TRY = Money(Decimal(0), Currency.TRY)

# The IRR is found by bisection until the bracket is this narrow; the bracket is widened by
# doubling its upper end, up to _IRR_SEARCH_LIMIT (100,000% a year), beyond which there is no IRR
# worth reporting.
_IRR_TOLERANCE = Decimal("0.0001")
_IRR_SEARCH_LIMIT = Decimal(1000)


@dataclass(frozen=True, slots=True)
class YearlyCashFlow:
    """One year of a System Option's cash flow. `year` counts from 1.

    `netted_kwh` is the year's Netted Energy and `netting_savings` the drop in the grid bill it
    brings; `exported_kwh` is the year's Exported Energy and `export_income` what it earns.
    """

    year: int
    production_kwh: Decimal
    netted_kwh: Decimal
    exported_kwh: Decimal
    netting_savings: Money
    export_income: Money
    annual_savings: Money
    inverter_replacement: Money
    net_savings: Money
    cumulative_net_savings: Money


@dataclass(frozen=True, slots=True)
class SavingsAnalysis:
    """What a System Option saves the Customer.

    `netted_share` is year 1's Netted Energy over its production (0 when nothing is produced).
    `payback_years` is None, with `payback_beyond_lifetime` set, when the total price is not
    recovered within the lifetime. `inverter_replaced_within_lifetime` says whether the cash
    flow contains an inverter replacement, which it does only when the replacement year is
    within the lifetime.

    `npv` is the Net Present Value at the real Discount Rate and `irr` the Internal Rate of
    Return (a share per year, 0.12 is 12%); both are unrounded. `irr` is None exactly when the
    total price is not recovered within the lifetime, the case of `payback_beyond_lifetime`.
    """

    cash_flow: tuple[YearlyCashFlow, ...]
    first_year_annual_savings: Money
    lifetime_savings: Money
    netted_share: Decimal
    payback_years: Decimal | None
    payback_beyond_lifetime: bool
    inverter_replaced_within_lifetime: bool
    npv: Money
    irr: Decimal | None


def analyze_savings(
    *,
    year1_monthly_production_kwh: tuple[Decimal, ...],
    monthly_consumption_kwh: Decimal,
    degradation_rate_per_year: Decimal,
    tariff: ResidentialTariff,
    financial: FinancialAssumptions,
    inverter_price_incl_vat: Money,
    total_price_incl_vat: Money,
) -> SavingsAnalysis:
    """Build the cash flow over the lifetime and find the Payback Period.

    In year n, month m's production is year 1's x (1 - degradation)^(n-1). Under Monthly Netting
    the month's Netted Energy is min(production, Monthly Consumption) and the rest is Exported
    Energy. A month's bill drop is cost_m(consumption) - cost_m(consumption - Netted Energy)
    with that month's Tariff Tiers, so Netted Energy comes off the high tier first. Annual
    Savings are the bill drops plus Exported Energy x Export Price, both grown by
    (1 + tariff escalation)^(n-1). The inverter replacement costs today's price x
    (1 + equipment escalation)^(year - 1) and is subtracted from that year's net savings.
    Payback is (n - 1) + remaining / net savings of the first year n whose cumulative net
    savings reach `total_price_incl_vat`.

    NPV = -total price + sum over the lifetime of net savings(n) / (1 + r)^n, with r the real
    Discount Rate. The IRR is the r at which that NPV is zero, found by bisection to 0.0001;
    it is absent when the NPV at r = 0 is negative (the price is not recovered).
    """
    if len(year1_monthly_production_kwh) != MONTHS_PER_YEAR:
        raise ValueError("savings need exactly 12 monthly production values")
    if monthly_consumption_kwh < 0:
        raise ValueError("monthly consumption must not be negative")
    total_price = _in_try(total_price_incl_vat)
    inverter_price = _in_try(inverter_price_incl_vat)

    # The year-1 bill of each month does not change with the year.
    monthly_bill = [
        tariff.monthly_cost(month, monthly_consumption_kwh).amount
        for month in range(1, MONTHS_PER_YEAR + 1)
    ]

    rows: list[YearlyCashFlow] = []
    cumulative = _ZERO_TRY
    payback_years: Decimal | None = None
    netted_share = Decimal(0)
    for year in range(1, financial.lifetime_years + 1):
        degradation_factor = (1 - degradation_rate_per_year) ** (year - 1)
        production = Decimal(0)
        netted = Decimal(0)
        bill_drop = Decimal(0)
        for month, year1_production in enumerate(year1_monthly_production_kwh, start=1):
            month_production = year1_production * degradation_factor
            month_netted = min(month_production, monthly_consumption_kwh)
            production += month_production
            netted += month_netted
            bill_drop += (
                monthly_bill[month - 1]
                - tariff.monthly_cost(month, monthly_consumption_kwh - month_netted).amount
            )
        exported = production - netted
        tariff_factor = (1 + financial.tariff_escalation_rate_real) ** (year - 1)

        netting_savings = Money(bill_drop * tariff_factor, Currency.TRY)
        export_income = Money(
            exported * tariff.export_price_try_per_kwh * tariff_factor, Currency.TRY
        )
        annual_savings = netting_savings + export_income
        replacement = (
            inverter_price * ((1 + financial.equipment_escalation_rate_real) ** (year - 1))
            if year == financial.inverter_replacement_year
            else _ZERO_TRY
        )
        net_savings = annual_savings - replacement
        previous_cumulative = cumulative
        cumulative = cumulative + net_savings

        if year == 1 and production > 0:
            netted_share = netted / production
        if (
            payback_years is None
            and previous_cumulative.amount < total_price.amount <= cumulative.amount
        ):
            remaining = total_price - previous_cumulative
            payback_years = (year - 1) + remaining.amount / net_savings.amount

        rows.append(
            YearlyCashFlow(
                year=year,
                production_kwh=production,
                netted_kwh=netted,
                exported_kwh=exported,
                netting_savings=netting_savings,
                export_income=export_income,
                annual_savings=annual_savings,
                inverter_replacement=replacement,
                net_savings=net_savings,
                cumulative_net_savings=cumulative,
            )
        )

    yearly_net_savings = [row.net_savings.amount for row in rows]
    return SavingsAnalysis(
        cash_flow=tuple(rows),
        first_year_annual_savings=rows[0].annual_savings,
        lifetime_savings=cumulative,
        netted_share=netted_share,
        payback_years=payback_years,
        payback_beyond_lifetime=payback_years is None,
        inverter_replaced_within_lifetime=(
            financial.inverter_replacement_year <= financial.lifetime_years
        ),
        npv=Money(
            _net_present_value(
                yearly_net_savings, total_price.amount, financial.discount_rate_real
            ),
            Currency.TRY,
        ),
        irr=_internal_rate_of_return(yearly_net_savings, total_price.amount),
    )


def _net_present_value(
    net_savings: Sequence[Decimal], total_price_try: Decimal, rate: Decimal
) -> Decimal:
    """-price at year 0 plus each year's net savings discounted by (1 + rate)^year."""
    return -total_price_try + sum(
        (amount / (1 + rate) ** year for year, amount in enumerate(net_savings, start=1)),
        start=Decimal(0),
    )


def _internal_rate_of_return(
    net_savings: Sequence[Decimal], total_price_try: Decimal
) -> Decimal | None:
    """The rate at which the NPV is zero, to `_IRR_TOLERANCE`; None when it is negative at 0.

    The NPV falls as the rate rises, so the root is bracketed by [0, upper] where the NPV is
    non-negative at 0 and negative at `upper`, and the bracket is halved until it is narrow.
    """
    npv_at_zero = _net_present_value(net_savings, total_price_try, Decimal(0))
    if npv_at_zero < 0:
        return None
    if npv_at_zero == 0:
        return Decimal(0)
    lower = Decimal(0)
    upper = Decimal(1)
    while _net_present_value(net_savings, total_price_try, upper) > 0:
        lower = upper
        upper *= 2
        if upper > _IRR_SEARCH_LIMIT:
            return None
    while upper - lower > _IRR_TOLERANCE:
        middle = (lower + upper) / 2
        if _net_present_value(net_savings, total_price_try, middle) > 0:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def _in_try(money: Money) -> Money:
    if money.currency is not Currency.TRY:
        raise CurrencyMismatchError(Currency.TRY, money.currency)
    return money
