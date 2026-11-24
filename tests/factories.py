"""Plain builders for the domain objects every test layer needs.

Defaults are round numbers chosen so expected values can be worked out by hand:
a 500 W, 2.0 m2 panel, a specific yield of 1,500 kWh/kWp and a coverage ratio of 0.80.
Override only what a test is about.
"""

from datetime import date
from decimal import Decimal

from sunquote.domain.assumptions import EngineeringAssumptions
from sunquote.domain.catalog import Catalog, Panel
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
from sunquote.domain.production import SpecificYield, SpecificYieldInputs

QUOTE_DATE = date(2026, 11, 24)

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
    )


def make_catalog() -> Catalog:
    panel = make_panel()
    return Catalog(panels=(panel,), default_panel_id=panel.panel_id)


def make_assumptions(
    *,
    pitched_coverage_ratio: str = "0.80",
    flat_roof_tilt_deg: str = "15",
    system_loss_percent: str = "14",
) -> EngineeringAssumptions:
    return EngineeringAssumptions(
        coverage_ratio_by_roof_type={
            RoofType.PITCHED: Decimal(pitched_coverage_ratio),
            RoofType.FLAT: Decimal("0.50"),
        },
        flat_roof_tilt_deg=Decimal(flat_roof_tilt_deg),
        system_loss_percent=Decimal(system_loss_percent),
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
