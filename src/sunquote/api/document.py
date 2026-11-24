"""The printable Turkish quote document: a Jinja2 template filled from a stored Quote.

Every figure comes from the Quote through the rounding policy and the Turkish formatting in
`sunquote.api.turkish`. The prose slots (the Narrative) hold only text and `{placeholders}`
from the closed list in `sunquote.domain.placeholders`; `fill_narrative` replaces them with
those same formatted figures, so the writer of the Narrative (ADR 0001) can change the words
without touching a number. A Quote's stored Narrative is shown when its source is `llm`; else
the fixed Turkish text below, which belongs to this layer.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sunquote.api import turkish
from sunquote.domain import rounding
from sunquote.domain.narrative import NarrativeDraft, NarrativeSource
from sunquote.domain.placeholders import PAYBACK_YEARS, fill_placeholders, option_placeholder
from sunquote.domain.ports import StoredQuote
from sunquote.domain.quote import SystemOption
from sunquote.domain.sizing import BindingLimit, SizingStrategy

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "quote_document.html"

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
class FilledNarrative:
    """The prose slots with every placeholder filled. `options_comparison` is None unless the
    Quote has two System Options."""

    greeting: str
    summary: str
    options_comparison: str | None
    next_steps: str


FIXED_GREETING = "Sayın {customer_name},"
FIXED_SUMMARY = (
    "Çatınız ve elektrik tüketiminiz için hazırladığımız teklif aşağıdadır. İlk seçenek "
    "{option_1_capacity_kwp} kWp gücünde bir sistemdir; yılda yaklaşık "
    "{option_1_annual_production_kwh} kWh elektrik üretmesi ve KDV dahil "
    "{option_1_total_try} tutarında olması beklenmektedir."
)
FIXED_OPTIONS_COMPARISON = (
    "İki seçenek boyut ve fiyat bakımından farklıdır: ilk seçenek {option_1_capacity_kwp} kWp "
    "ve {option_1_total_try}, ikinci seçenek {option_2_capacity_kwp} kWp ve "
    "{option_2_total_try} tutarındadır (KDV dahil). Hangisinin size uygun olduğunu "
    "birlikte değerlendirebiliriz."
)
FIXED_NEXT_STEPS = (
    "Teklifteki fiyatlar {valid_until} tarihine kadar, yani {validity_period_days} gün "
    "geçerlidir. Teklifi onaylamak veya sorularınız için bizimle iletişime geçebilirsiniz."
)


def fixed_draft(option_count: int) -> NarrativeDraft:
    """The template's fixed Turkish text, for a Quote with `option_count` System Options.

    It follows the same rules as a written draft: no digits, only available placeholders and a
    comparison only with two options.
    """
    return NarrativeDraft(
        greeting=FIXED_GREETING,
        summary=FIXED_SUMMARY,
        next_steps=FIXED_NEXT_STEPS,
        options_comparison=FIXED_OPTIONS_COMPARISON if option_count == 2 else None,
    )


def fill_narrative(draft: NarrativeDraft, figures: Mapping[str, str]) -> FilledNarrative:
    """Replace every `{placeholder}` with its formatted figure. An unknown one raises KeyError."""
    comparison = draft.options_comparison
    return FilledNarrative(
        greeting=fill_placeholders(draft.greeting, figures),
        summary=fill_placeholders(draft.summary, figures),
        options_comparison=(
            fill_placeholders(comparison, figures) if comparison and comparison.strip() else None
        ),
        next_steps=fill_placeholders(draft.next_steps, figures),
    )


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


@dataclass(frozen=True, slots=True)
class AssumptionView:
    label: str
    text: str


def _site_label(stored: StoredQuote) -> str:
    """The resolved Address when the Site has one, else its Coordinates."""
    recorded = stored.quote.assumptions
    if recorded.geocoding_result is not None:
        return recorded.geocoding_result.display_name
    coordinates = recorded.submitted_request.site.coordinates
    assert coordinates is not None
    north_south = "K" if coordinates.latitude >= 0 else "G"
    east_west = "D" if coordinates.longitude >= 0 else "B"
    return (
        f"{turkish.format_decimal(abs(coordinates.latitude))}° {north_south}, "
        f"{turkish.format_decimal(abs(coordinates.longitude))}° {east_west}"
    )


def _try(amount: Decimal) -> str:
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
        sale_price=_try(option.price.sale_price.amount),
        vat=_try(option.price.vat.amount),
        vat_rate=turkish.format_percent(vat_rate),
        total=_try(option.price.total.amount),
        first_year_savings=_try(savings.first_year_annual_savings.amount),
        payback=(
            "" if payback is None else turkish.format_decimal(rounding.round_payback_years(payback))
        ),
        payback_beyond_lifetime=savings.payback_beyond_lifetime,
        lifetime_savings=_try(savings.lifetime_savings.amount),
        lifetime_years=lifetime_years,
    )


def _assumption_views(stored: StoredQuote) -> tuple[AssumptionView, ...]:
    quote = stored.quote
    recorded = quote.assumptions
    tariff = recorded.tariff
    rate = recorded.exchange_rate
    financial = recorded.financial
    pricing = recorded.pricing
    panel = recorded.default_panel
    power = recorded.contracted_power
    rate_source = (
        "Satış temsilcisi tarafından belirlenen kur" if rate.overridden else "TCMB döviz satış kuru"
    )
    replacement = (
        f"İnverterin {financial.inverter_replacement_year}. yılda yenilenmesi hesaba katıldı."
        if quote.system_options[0].savings.inverter_replaced_within_lifetime
        else "Analiz süresi içinde inverter yenilemesi gerekmediği varsayıldı."
    )
    threshold = turkish.format_int(rounding.round_kwh(tariff.tier_threshold_kwh_per_year))
    annual_consumption = turkish.format_int(rounding.round_kwh(recorded.annual_consumption_kwh))
    low = turkish.format_try_per_kwh(tariff.low_tariff_try_per_kwh)
    high = turkish.format_try_per_kwh(tariff.high_tariff_try_per_kwh)
    export = turkish.format_try_per_kwh(tariff.export_price_try_per_kwh)
    tariff_escalation = turkish.format_percent(financial.tariff_escalation_rate_real)
    equipment_escalation = turkish.format_percent(financial.equipment_escalation_rate_real)
    system_loss = turkish.format_decimal(recorded.pvgis_inputs.system_loss_percent)
    bill = recorded.submitted_request.consumption.monthly_bill_try
    if recorded.consumption_derived_from_bill and bill is not None:
        consumption_text = (
            f"Aylık elektrik faturanız {_try(bill)} olarak belirtildi; yukarıdaki tarifeyle "
            f"bu fatura yıllık {annual_consumption} kWh tüketime karşılık gelir ve hesap bu "
            f"tüketimle yapıldı."
        )
    else:
        consumption_text = f"Yıllık tüketiminiz {annual_consumption} kWh olarak alındı."
    return (
        AssumptionView(
            "Döviz kuru",
            f"Ekipman fiyatları döviz cinsindendir ve 1 {rate.base} = "
            f"{turkish.format_decimal(rounding.round_exchange_rate(rate.rate))} {rate.quote} "
            f"kuruyla çevrildi ({rate_source}, {turkish.format_date(rate.rate_date)}).",
        ),
        AssumptionView("KDV", f"Fiyatlara {turkish.format_percent(pricing.vat_rate)} KDV eklenir."),
        AssumptionView("Elektrik tüketimi", consumption_text),
        AssumptionView(
            "Elektrik tarifesi",
            f"Yıllık {threshold} kWh değerine kadar olan tüketim {low}, bu değerin üzerindeki "
            f"kısım {high} üzerinden hesaplandı (vergiler ve bedeller dahil, kademeli tarife). "
            f"Tarife {turkish.format_date(tariff.valid_from)} tarihinden itibaren geçerlidir.",
        ),
        AssumptionView(
            "Şebekeye satış fiyatı",
            f"Şebekeye verilen fazla enerji {export} üzerinden değerlendirildi.",
        ),
        AssumptionView(
            "Öz tüketim oranı",
            f"Üretimin {turkish.format_percent(tariff.self_consumption_ratio)} kadarının kendi "
            f"tüketiminizde kullanıldığı, kalanının şebekeye satıldığı varsayıldı.",
        ),
        AssumptionView(
            "Fiyat artışı ve bugünkü lira",
            f"Elektrik fiyatlarının yıllık reel artışı {tariff_escalation}, ekipman "
            f"fiyatlarının {equipment_escalation} olarak alındı. Bu oranlar enflasyondan "
            f"arındırılmış (reel) oranlar olduğu için {financial.lifetime_years} yıllık tüm "
            f"tasarruf ve geri ödeme rakamları bugünkü lira cinsindendir; ileride "
            f"faturalarınızda göreceğiniz nominal tutarlarla aynı olmayabilir.",
        ),
        AssumptionView(
            "Panel performansı",
            f"Panel üretimi her yıl {turkish.format_percent(panel.degradation_rate_per_year)} "
            f"azalır. Üretim tahmini PVGIS verisiyle ve %{system_loss} sistem kaybı "
            f"varsayımıyla hesaplandı. {replacement}",
        ),
        AssumptionView(
            "Sözleşme gücü",
            f"{turkish.format_decimal(power.kw)} kW "
            f"({'belirttiğiniz değer' if power.given else 'varsayılan değer'}); sistem bu "
            f"güce göre sınırlandı.",
        ),
        AssumptionView(
            "Geçerlilik süresi",
            f"Fiyatlar {pricing.validity_period_days} gün, "
            f"{turkish.format_date(quote.valid_until)} tarihine kadar geçerlidir.",
        ),
    )


def _figures(options: tuple[OptionView, ...], stored: StoredQuote) -> dict[str, str]:
    """The display value of every placeholder the Quote can fill (the closed list in
    `sunquote.domain.placeholders`). An option beyond its lifetime has no payback figure."""
    quote = stored.quote
    figures = {
        "customer_name": quote.customer.name,
        "quote_number": quote.quote_number,
        "valid_until": turkish.format_date(quote.valid_until),
        "validity_period_days": turkish.format_int(quote.assumptions.pricing.validity_period_days),
    }
    for option in options:
        values = {
            "capacity_kwp": option.capacity_kwp,
            "panel_count": option.panel_count,
            "panel_model": option.panel_model,
            "inverter_model": option.inverter_model,
            "annual_production_kwh": option.annual_production_kwh,
            "sale_price_try": option.sale_price,
            "vat_try": option.vat,
            "total_try": option.total,
            "first_year_savings_try": option.first_year_savings,
            "lifetime_savings_try": option.lifetime_savings,
        }
        if not option.payback_beyond_lifetime:
            values[PAYBACK_YEARS] = option.payback
        for name, figure in values.items():
            figures[option_placeholder(option.number, name)] = figure
    return figures


def _option_views(stored: StoredQuote) -> tuple[OptionView, ...]:
    recorded = stored.quote.assumptions
    return tuple(
        _option_view(number, option, recorded.financial.lifetime_years, recorded.pricing.vat_rate)
        for number, option in enumerate(stored.quote.system_options, start=1)
    )


def stored_narrative(stored: StoredQuote) -> FilledNarrative:
    """The Narrative a stored Quote shows: its stored draft when the source is `llm`, else the
    fixed text, with every placeholder filled from the Quote. It reads only the stored Quote."""
    record = stored.quote.narrative
    draft = record.draft
    if record.source is not NarrativeSource.LLM or draft is None:
        draft = fixed_draft(len(stored.quote.system_options))
    return fill_narrative(draft, _figures(_option_views(stored), stored))


_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_quote_document(stored: StoredQuote) -> str:
    """The Quote as one printable Turkish HTML page."""
    quote = stored.quote
    return _environment.get_template(TEMPLATE_NAME).render(
        quote_number=quote.quote_number,
        quote_date=turkish.format_date(quote.quote_date),
        valid_until=turkish.format_date(quote.valid_until),
        customer_name=quote.customer.name,
        site=_site_label(stored),
        options=_option_views(stored),
        narrative=stored_narrative(stored),
        assumptions=_assumption_views(stored),
    )
