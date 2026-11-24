"""The displayed form of a Quote's System Options: every figure as a Turkish-formatted string.

The quote document's template and the Narrative's placeholders (`sunquote.api.narrative_text`)
both read these views, so a figure is rounded and formatted in one place.
"""

from dataclasses import dataclass
from decimal import Decimal

from sunquote.api import turkish
from sunquote.domain import rounding
from sunquote.domain.ports import StoredQuote
from sunquote.domain.quote import SystemOption
from sunquote.domain.sizing import BindingLimit, SizingStrategy

STRATEGY_TITLES = {
    SizingStrategy.CONSUMPTION_MATCHED: "Tüketime göre boyutlandırma",
    SizingStrategy.ROOF_MAX: "Çatıya göre boyutlandırma",
}
STRATEGY_EXPLANATIONS = {
    SizingStrategy.CONSUMPTION_MATCHED: (
        "Sistem, yıllık üretimi yıllık elektrik tüketiminize yaklaştıracak büyüklükte seçildi."
    ),
    SizingStrategy.ROOF_MAX: "Sistem, çatınıza sığan en çok paneli yerleştirecek şekilde seçildi.",
}
BINDING_LIMIT_EXPLANATIONS = {
    BindingLimit.ROOF: "Çatınızın panel yerleştirmeye uygun alanı sistemin büyüklüğünü sınırladı.",
    BindingLimit.CONSUMPTION_TARGET: (
        "Yıllık tüketiminizi karşılayacak üretim hedefine ulaşıldığı için sistem daha fazla "
        "büyütülmedi."
    ),
    BindingLimit.CONTRACTED_POWER: (
        "Şebeke bağlantı anlaşmanızdaki sözleşme gücü sistemin büyüklüğünü sınırladı."
    ),
}


@dataclass(frozen=True, slots=True)
class MonthView:
    name: str
    production_kwh: str
    bar_percent: int


@dataclass(frozen=True, slots=True)
class OptionView:
    number: int
    strategy_title: str
    strategy_explanation: str
    binding_limit_explanation: str
    panel_count: str
    panel_name: str
    panel_model: str
    inverter_name: str
    inverter_model: str
    capacity_kwp: str
    annual_production_kwh: str
    months: tuple[MonthView, ...]
    sale_price: str
    vat: str
    vat_rate: str
    total: str
    first_year_savings: str
    payback: str
    payback_beyond_lifetime: bool
    lifetime_savings: str
    lifetime_years: int


def display_try(amount: Decimal) -> str:
    """An amount in TRY, rounded by the policy and formatted the Turkish way."""
    return turkish.format_try(rounding.round_try(amount))


def _option_view(
    number: int, option: SystemOption, lifetime_years: int, vat_rate: Decimal
) -> OptionView:
    monthly = [rounding.round_kwh(kwh) for kwh in option.monthly_production_kwh]
    peak = max(monthly) or 1
    savings = option.savings
    payback = savings.payback_years
    return OptionView(
        number=number,
        strategy_title=STRATEGY_TITLES[option.strategy],
        strategy_explanation=STRATEGY_EXPLANATIONS[option.strategy],
        binding_limit_explanation=BINDING_LIMIT_EXPLANATIONS[option.binding_limit],
        panel_count=turkish.format_int(option.panel_count),
        panel_name=f"{option.panel.manufacturer} {option.panel.model} ({option.panel.power_w} W)",
        panel_model=f"{option.panel.manufacturer} {option.panel.model}",
        inverter_name=(
            f"{option.inverter.manufacturer} {option.inverter.model} "
            f"({turkish.format_decimal(option.inverter.ac_power_kw)} kW)"
        ),
        inverter_model=f"{option.inverter.manufacturer} {option.inverter.model}",
        capacity_kwp=turkish.format_decimal(rounding.round_capacity_kwp(option.capacity_kwp)),
        annual_production_kwh=turkish.format_int(rounding.round_kwh(option.annual_production_kwh)),
        months=tuple(
            MonthView(
                name=name,
                production_kwh=turkish.format_int(kwh),
                bar_percent=round(100 * kwh / peak),
            )
            for name, kwh in zip(turkish.MONTH_NAMES, monthly, strict=True)
        ),
        sale_price=display_try(option.price.sale_price.amount),
        vat=display_try(option.price.vat.amount),
        vat_rate=turkish.format_percent(vat_rate),
        total=display_try(option.price.total.amount),
        first_year_savings=display_try(savings.first_year_annual_savings.amount),
        payback=(
            "" if payback is None else turkish.format_decimal(rounding.round_payback_years(payback))
        ),
        payback_beyond_lifetime=savings.payback_beyond_lifetime,
        lifetime_savings=display_try(savings.lifetime_savings.amount),
        lifetime_years=lifetime_years,
    )


def option_views(stored: StoredQuote) -> tuple[OptionView, ...]:
    """One view per System Option, numbered from 1 like the Narrative's option placeholders."""
    recorded = stored.quote.assumptions
    return tuple(
        _option_view(number, option, recorded.financial.lifetime_years, recorded.pricing.vat_rate)
        for number, option in enumerate(stored.quote.system_options, start=1)
    )
