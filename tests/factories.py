"""Plain builders for the domain objects every test layer needs.

Defaults are round numbers chosen so expected values can be worked out by hand:
a 500 W, 2.0 m2 panel at USD 100, a specific yield of 1,500 kWh/kWp, a coverage ratio of 0.80
and an exchange rate of 40 TRY/USD.
Override only what a test is about.
"""

from datetime import date
from decimal import Decimal

from sunquote.domain.assumptions import (
    DcAcRatioRange,
    EngineeringAssumptions,
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog, Inverter, Panel
from sunquote.domain.model import (
    Consumption,
    Coordinates,
    Customer,
    QuoteRequest,
    Roof,
    RoofType,
    Site,
    SubscriberGroup,
)
from sunquote.domain.money import Currency, ExchangeRate, Money
from sunquote.domain.production import SpecificYield, SpecificYieldInputs
from sunquote.domain.tariff import ResidentialTariff

QUOTE_DATE = date(2026, 11, 24)
RATE_DATE = date(2026, 11, 23)  # the business day before QUOTE_DATE

# Sums to 1,500 kWh/kWp.
MONTHLY_YIELD_KWH_PER_KWP = tuple(
    Decimal(value) for value in (70, 90, 120, 140, 160, 175, 185, 170, 140, 110, 80, 60)
)


def make_panel() -> Panel:
    return Panel(
        panel_id="test-panel-500w",
        manufacturer="Test",
        model="T-500",
        power_w=500,
        length_mm=2000,
        width_mm=1000,
        degradation_rate_per_year=Decimal("0.005"),
        unit_price=Money(Decimal(100), Currency.USD),
    )


def make_inverter(inverter_id: str, ac_power_kw: str, usd_price: str) -> Inverter:
    return Inverter(
        inverter_id=inverter_id,
        manufacturer="Test",
        model=inverter_id.upper(),
        ac_power_kw=Decimal(ac_power_kw),
        unit_price=Money(Decimal(usd_price), Currency.USD),
    )


# For the default 4.0 kWp system (DC/AC range 1.00-1.30): "i3" is the cheapest but its ratio is
# 1.33, "i4" is 1.00 and "i35" is 1.14 (the cheapest compatible one), "i6" is oversized (0.67).
# "i05", "i25" and "i8" cover the one-panel (0.5 kWp), five-panel (2.5 kWp) and 16-panel (8 kWp)
# systems of the sizing and flat-roof tests.
DEFAULT_INVERTERS = (
    make_inverter("i05", "0.5", "300"),
    make_inverter("i25", "2.5", "400"),
    make_inverter("i3", "3", "500"),
    make_inverter("i4", "4", "700"),
    make_inverter("i35", "3.5", "650"),
    make_inverter("i6", "6", "900"),
    make_inverter("i8", "8", "1100"),
)


def make_catalog(inverters: tuple[Inverter, ...] = DEFAULT_INVERTERS) -> Catalog:
    panel = make_panel()
    return Catalog(panels=(panel,), default_panel_id=panel.panel_id, inverters=inverters)


def make_exchange_rate(rate: str = "40", *, overridden: bool = False) -> ExchangeRate:
    return ExchangeRate(
        base=Currency.USD,
        quote=Currency.TRY,
        rate=Decimal(rate),
        rate_date=RATE_DATE,
        overridden=overridden,
    )


def make_pricing_assumptions(
    *,
    bos_usd_per_kwp: str = "100",
    labour_try_per_kwp: str = "3000",
    fixed_project_cost_try: str = "20000",
    margin: str = "0.25",
    vat_rate: str = "0.20",
) -> PricingAssumptions:
    return PricingAssumptions(
        bos_price_per_kwp=Money(Decimal(bos_usd_per_kwp), Currency.USD),
        labour_price_per_kwp=Money(Decimal(labour_try_per_kwp), Currency.TRY),
        fixed_project_cost=Money(Decimal(fixed_project_cost_try), Currency.TRY),
        margin=Decimal(margin),
        vat_rate=Decimal(vat_rate),
    )


def make_assumptions(
    *,
    pitched_coverage_ratio: str = "0.80",
    flat_roof_tilt_deg: str = "15",
    system_loss_percent: str = "14",
    dc_ac_ratio_min: str = "1.00",
    dc_ac_ratio_max: str = "1.30",
) -> EngineeringAssumptions:
    return EngineeringAssumptions(
        coverage_ratio_by_roof_type={
            RoofType.PITCHED: Decimal(pitched_coverage_ratio),
            RoofType.FLAT: Decimal("0.50"),
        },
        flat_roof_tilt_deg=Decimal(flat_roof_tilt_deg),
        system_loss_percent=Decimal(system_loss_percent),
        dc_ac_ratio_range=DcAcRatioRange(
            minimum=Decimal(dc_ac_ratio_min), maximum=Decimal(dc_ac_ratio_max)
        ),
    )


def make_financial_assumptions(
    *,
    tariff_escalation: str = "0.02",
    equipment_escalation: str = "0",
    lifetime_years: int = 25,
    replacement_year: int = 12,
) -> FinancialAssumptions:
    return FinancialAssumptions(
        tariff_escalation_rate_real=Decimal(tariff_escalation),
        equipment_escalation_rate_real=Decimal(equipment_escalation),
        lifetime_years=lifetime_years,
        inverter_replacement_year=replacement_year,
    )


def make_tariff(
    *,
    threshold_kwh_per_year: str = "3000",
    low_try_per_kwh: str = "3",
    high_try_per_kwh: str = "5",
    export_try_per_kwh: str = "2",
    self_consumption_ratio: str = "0.8",
) -> ResidentialTariff:
    return ResidentialTariff(
        tier_threshold_kwh_per_year=Decimal(threshold_kwh_per_year),
        low_tariff_try_per_kwh=Decimal(low_try_per_kwh),
        high_tariff_try_per_kwh=Decimal(high_try_per_kwh),
        export_price_try_per_kwh=Decimal(export_try_per_kwh),
        self_consumption_ratio=Decimal(self_consumption_ratio),
        valid_from=date(2026, 4, 4),
        source="test tariff",
    )


def make_specific_yield(
    *,
    annual: str = "1500",
    monthly: tuple[Decimal, ...] = MONTHLY_YIELD_KWH_PER_KWP,
    tilt_deg: str = "30",
) -> SpecificYield:
    return SpecificYield(
        annual_kwh_per_kwp=Decimal(annual),
        monthly_kwh_per_kwp=monthly,
        inputs=SpecificYieldInputs(
            source="test",
            latitude=Decimal("39.930"),
            longitude=Decimal("32.860"),
            tilt_deg=Decimal(tilt_deg),
            aspect_deg=Decimal("0"),
            system_loss_percent=Decimal("14"),
        ),
    )


def make_request(
    *,
    usable_area_m2: str = "40",
    monthly_consumption_kwh: str = "500",
    azimuth_deg: str = "180",
    tilt_deg: str = "30",
    roof_type: RoofType = RoofType.PITCHED,
) -> QuoteRequest:
    return QuoteRequest(
        customer=Customer(name="Şule Öztürk", phone="+90 555 000 00 00", email="sule@example.com"),
        site=Site(
            coordinates=Coordinates(latitude=Decimal("39.9334"), longitude=Decimal("32.8597")),
            roof=Roof(
                roof_type=roof_type,
                usable_area_m2=Decimal(usable_area_m2),
                azimuth_deg=Decimal(azimuth_deg),
                tilt_deg=Decimal(tilt_deg),
            ),
        ),
        consumption=Consumption(monthly_consumption_kwh=Decimal(monthly_consumption_kwh)),
        subscriber_group=SubscriberGroup.RESIDENTIAL,
    )
