"""Annual Savings under Monthly Netting, the yearly cash flow and the Payback Period of one
System Option (ADR 0005).

Everything is TRY in today's lira: the escalation rates are real (ADR 0003), and the Payback
Period is undiscounted. Nothing here rounds; rounding is the display policy.
"""

from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.assumptions import FinancialAssumptions
from sunquote.domain.errors import CurrencyMismatchError
from sunquote.domain.money import Currency, Money
from sunquote.domain.tariff import MONTHS_PER_YEAR, ResidentialTariff

_ZERO_TRY = Money(Decimal(0), Currency.TRY)


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
    """

    cash_flow: tuple[YearlyCashFlow, ...]
    first_year_annual_savings: Money
    lifetime_savings: Money
    netted_share: Decimal
    payback_years: Decimal | None
    payback_beyond_lifetime: bool
    inverter_replaced_within_lifetime: bool


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
    )


def _in_try(money: Money) -> Money:
    if money.currency is not Currency.TRY:
        raise CurrencyMismatchError(Currency.TRY, money.currency)
    return money
