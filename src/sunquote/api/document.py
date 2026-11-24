"""The printable Turkish quote document: a Jinja2 template filled from a stored Quote.

Every figure comes from the Quote through the rounding policy and the Turkish formatting in
`sunquote.api.turkish`. The prose slots (the `Narrative`) hold only text and `{placeholders}`
from a closed list; `fill_narrative` replaces them with those same formatted figures, so a
later writer of the Narrative (ADR 0001) can change the words without touching a number.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sunquote.api import turkish
from sunquote.domain import rounding
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
class Narrative:
    """The prose slots of the document. Text may name placeholders such as
    `{option_1_capacity_kwp}` but never writes a figure itself (ADR 0001)."""

    greeting: str
    summary: str
    options_comparison: str
    next_steps: str


DEFAULT_NARRATIVE = Narrative(
    greeting="Sayın {customer_name},",
    summary=(
        "Çatınız ve elektrik tüketiminiz için hazırladığımız teklif aşağıdadır. İlk seçenek "
        "{option_1_capacity_kwp} kWp gücünde bir sistemdir; yılda yaklaşık "
        "{option_1_annual_production_kwh} kWh elektrik üretmesi ve KDV dahil "
        "{option_1_total_try} tutarında olması beklenmektedir."
    ),
    options_comparison=(
        "İki seçenek boyut ve fiyat bakımından farklıdır: ilk seçenek {option_1_capacity_kwp} kWp "
        "ve {option_1_total_try}, ikinci seçenek {option_2_capacity_kwp} kWp ve "
        "{option_2_total_try} tutarındadır (KDV dahil). Hangisinin size uygun olduğunu "
        "birlikte değerlendirebiliriz."
    ),
    next_steps=(
        "Teklifteki fiyatlar {valid_until} tarihine kadar, yani {validity_period_days} gün "
        "geçerlidir. Teklifi onaylamak veya sorularınız için bizimle iletişime geçebilirsiniz."
    ),
)


def fill_narrative(narrative: Narrative, figures: Mapping[str, str]) -> Narrative:
    """Replace every `{placeholder}` with its formatted figure. An unknown one raises KeyError."""
    return Narrative(
        greeting=narrative.greeting.format_map(figures),
        summary=narrative.summary.format_map(figures),
        options_comparison=narrative.options_comparison.format_map(figures),
        next_steps=narrative.next_steps.format_map(figures),
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
    inverter_name: str
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
    site = stored.quote.assumptions.submitted_request.site
    address = getattr(site, "address", None)
    if address:
        text = str(address)
        extras = [part for part in (stored.district, stored.province) if part and part not in text]
        return ", ".join([text, *extras])
    coordinates = site.coordinates
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
        inverter_name=(
            f"{option.inverter.manufacturer} {option.inverter.model} "
            f"({turkish.format_decimal(option.inverter.ac_power_kw)} kW)"
        ),
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
        if financial.inverter_replacement_year <= financial.lifetime_years
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
    return (
        AssumptionView(
            "Döviz kuru",
            f"Ekipman fiyatları döviz cinsindendir ve 1 {rate.base} = "
            f"{turkish.format_decimal(rounding.round_exchange_rate(rate.rate))} {rate.quote} "
            f"kuruyla çevrildi ({rate_source}, {turkish.format_date(rate.rate_date)}).",
        ),
        AssumptionView("KDV", f"Fiyatlara {turkish.format_percent(pricing.vat_rate)} KDV eklenir."),
        AssumptionView(
            "Elektrik tüketimi", f"Yıllık tüketiminiz {annual_consumption} kWh olarak alındı."
        ),
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
    quote = stored.quote
    figures = {
        "customer_name": quote.customer.name,
        "quote_number": quote.quote_number,
        "valid_until": turkish.format_date(quote.valid_until),
        "validity_period_days": turkish.format_int(quote.assumptions.pricing.validity_period_days),
    }
    for option in options:
        prefix = f"option_{option.number}_"
        figures[prefix + "capacity_kwp"] = option.capacity_kwp
        figures[prefix + "annual_production_kwh"] = option.annual_production_kwh
        figures[prefix + "total_try"] = option.total
        figures[prefix + "first_year_savings_try"] = option.first_year_savings
    return figures


_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_quote_document(stored: StoredQuote, narrative: Narrative = DEFAULT_NARRATIVE) -> str:
    """The Quote as one printable Turkish HTML page."""
    quote = stored.quote
    recorded = quote.assumptions
    options = tuple(
        _option_view(number, option, recorded.financial.lifetime_years, recorded.pricing.vat_rate)
        for number, option in enumerate(quote.system_options, start=1)
    )
    two_options = len(options) == 2
    if not two_options:
        # The comparison names two options, so it is neither filled nor shown with one.
        narrative = Narrative(narrative.greeting, narrative.summary, "", narrative.next_steps)
    filled = fill_narrative(narrative, _figures(options, stored))
    return _environment.get_template(TEMPLATE_NAME).render(
        quote_number=quote.quote_number,
        quote_date=turkish.format_date(quote.quote_date),
        valid_until=turkish.format_date(quote.valid_until),
        customer_name=quote.customer.name,
        site=_site_label(stored),
        options=options,
        two_options=two_options,
        narrative=filled,
        assumptions=_assumption_views(stored),
    )
