"""The printable Turkish quote document: a Jinja2 template filled from a stored Quote.

Every figure comes from the Quote through the rounding policy and the Turkish formatting in
`sunquote.api.turkish`. The option views (`sunquote.api.option_views`) and the Narrative
(`sunquote.api.narrative_text`, its placeholders filled from those same figures) are built once
per render and handed to the template.
"""

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sunquote.api import turkish
from sunquote.api.narrative_text import stored_narrative
from sunquote.api.option_views import display_try, option_views
from sunquote.domain import rounding
from sunquote.domain.ports import StoredQuote

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "quote_document.html"


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
    daily_allowance = turkish.format_decimal(tariff.tier_threshold_kwh_per_day)
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
            f"Aylık elektrik faturanız {display_try(bill)} olarak belirtildi; yukarıdaki tarifeyle "
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
            f"Her ay, günlük {daily_allowance} kWh sınırına (ayın gün sayısıyla çarpılır) kadar "
            f"olan tüketim {low}, bu sınırın üzerindeki kısım {high} üzerinden hesaplandı "
            f"(vergiler ve bedeller dahil, kademeli tarife). "
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
    options = option_views(stored)
    return _environment.get_template(TEMPLATE_NAME).render(
        quote_number=quote.quote_number,
        quote_date=turkish.format_date(quote.quote_date),
        valid_until=turkish.format_date(quote.valid_until),
        customer_name=quote.customer.name,
        site=_site_label(stored),
        options=options,
        narrative=stored_narrative(stored, options),
        assumptions=_assumption_views(stored),
    )
