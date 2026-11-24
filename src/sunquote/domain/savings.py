"""Annual Savings, the yearly cash flow and the Payback Period of one System Option.

Everything is TRY in today's lira: the escalation rates are real (ADR 0003), and the Payback
Period is undiscounted. Nothing here rounds; rounding is the display policy.
"""

from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.assumptions import FinancialAssumptions
from sunquote.domain.errors import CurrencyMismatchError
from sunquote.domain.money import Currency, Money
from sunquote.domain.tariff import ResidentialTariff

_ZERO_TRY = Money(Decimal(0), Currency.TRY)


@dataclass(frozen=True, slots=True)
class YearlyCashFlow:
    """One year of a System Option's cash flow. `year` counts from 1."""

    year: int
    production_kwh: Decimal
    self_consumed_kwh: Decimal
    exported_kwh: Decimal
    self_consumption_savings: Money
    export_income: Money
    annual_savings: Money
    inverter_replacement: Money
    net_savings: Money
    cumulative_net_savings: Money


@dataclass(frozen=True, slots=True)
class SavingsAnalysis:
    """What a System Option saves the Customer.

    `payback_years` is None, with `payback_beyond_lifetime` set, when the total price is not
    recovered within the lifetime.
    """

    cash_flow: tuple[YearlyCashFlow, ...]
    first_year_annual_savings: Money
    lifetime_savings: Money
    payback_years: Decimal | None
    payback_beyond_lifetime: bool


def analyze_savings(
    *,
    year1_production_kwh: Decimal,
    annual_consumption_kwh: Decimal,
    degradation_rate_per_year: Decimal,
    tariff: ResidentialTariff,
    financial: FinancialAssumptions,
    inverter_price_incl_vat: Money,
    total_price_incl_vat: Money,
) -> SavingsAnalysis:
    """Build the cash flow over the lifetime and find the Payback Period.

    In year n, production is year 1's x (1 - degradation)^(n-1). Self-consumed energy is
    production x Self-Consumption Ratio, capped at annual consumption, and is worth the drop in
    the annual grid cost, so it comes off the high Tariff Tier first. The rest is exported at the
    Export Price. Both tiers and the Export Price grow by (1 + tariff escalation)^(n-1).
    The inverter replacement costs today's price x (1 + equipment escalation)^(year - 1) and is
    subtracted from that year's net savings. Payback is (n - 1) + remaining / net savings of
    the first year n whose cumulative net savings reach `total_price_incl_vat`.
    """
    total_price = _in_try(total_price_incl_vat)
    inverter_price = _in_try(inverter_price_incl_vat)

    rows: list[YearlyCashFlow] = []
    cumulative = _ZERO_TRY
    payback_years: Decimal | None = None
    for year in range(1, financial.lifetime_years + 1):
        production = year1_production_kwh * (1 - degradation_rate_per_year) ** (year - 1)
        self_consumed = min(production * tariff.self_consumption_ratio, annual_consumption_kwh)
        exported = production - self_consumed
        tariff_factor = (1 + financial.tariff_escalation_rate_real) ** (year - 1)

        bill_drop = (
            tariff.annual_cost(annual_consumption_kwh).amount
            - tariff.annual_cost(annual_consumption_kwh - self_consumed).amount
        )
        self_consumption_savings = Money(bill_drop * tariff_factor, Currency.TRY)
        export_income = Money(
            exported * tariff.export_price_try_per_kwh * tariff_factor, Currency.TRY
        )
        annual_savings = self_consumption_savings + export_income
        replacement = (
            inverter_price * ((1 + financial.equipment_escalation_rate_real) ** (year - 1))
            if year == financial.inverter_replacement_year
            else _ZERO_TRY
        )
        net_savings = Money(annual_savings.amount - replacement.amount, Currency.TRY)
        previous_cumulative = cumulative
        cumulative = cumulative + net_savings

        if (
            payback_years is None
            and previous_cumulative.amount < total_price.amount <= cumulative.amount
        ):
            remaining = total_price.amount - previous_cumulative.amount
            payback_years = (year - 1) + remaining / net_savings.amount

        rows.append(
            YearlyCashFlow(
                year=year,
                production_kwh=production,
                self_consumed_kwh=self_consumed,
                exported_kwh=exported,
                self_consumption_savings=self_consumption_savings,
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
        payback_years=payback_years,
        payback_beyond_lifetime=payback_years is None,
    )


def _in_try(money: Money) -> Money:
    if money.currency is not Currency.TRY:
        raise CurrencyMismatchError(Currency.TRY, money.currency)
    return money
