"""The domain entry point, tested through `build_quote` with fixed inputs.

Fixed inputs: panel 0.5 kWp / 2.0 m2, coverage ratio 0.80, annual specific yield 1,500
kWh/kWp (monthly values sum to 1,500).
"""

from datetime import date
from decimal import Decimal

import pytest

from sunquote.domain.errors import NoViableSystemError
from sunquote.domain.model import RoofType
from sunquote.domain.quote import build_quote
from sunquote.domain.sizing import BindingLimit, SizingStrategy
from tests.factories import (
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_pricing_assumptions,
    make_request,
    make_specific_yield,
)


def build(
    *,
    usable_area_m2: str = "40",
    monthly_consumption_kwh: str = "500",
    annual_yield: str = "1500",
):
    return build_quote(
        request=make_request(
            usable_area_m2=usable_area_m2, monthly_consumption_kwh=monthly_consumption_kwh
        ),
        specific_yield=make_specific_yield(annual=annual_yield),
        catalog=make_catalog(),
        assumptions=make_assumptions(),
        pricing=make_pricing_assumptions(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )


@pytest.mark.parametrize(
    ("usable_area_m2", "monthly_kwh", "annual_yield", "panels", "limit"),
    [
        # target 6000/1500 = 4.0 kWp = 8 panels; roof fits 16 -> consumption target
        ("40", "500", "1500", 8, BindingLimit.CONSUMPTION_TARGET),
        # target 6000/1450 = 4.138 kWp = 8.28 panels -> rounds down to 8
        ("40", "500", "1450", 8, BindingLimit.CONSUMPTION_TARGET),
        # target 0.08 kWp = 0.16 panels -> at least one panel
        ("40", "10", "1500", 1, BindingLimit.CONSUMPTION_TARGET),
        # target 32 panels; roof fits floor(40*0.8/2) = 16 -> roof
        ("40", "2000", "1500", 16, BindingLimit.ROOF),
        # roof fits floor(41*0.8/2) = floor(16.4) = 16 -> roof rounds down
        ("41", "2000", "1500", 16, BindingLimit.ROOF),
        # tie: roof fits 8 and target is 8 panels -> the Roof counts as binding
        ("20", "500", "1500", 8, BindingLimit.ROOF),
        # one panel fits (2.5*0.8/2 = 1) and the target is also one -> Roof (tie)
        ("2.5", "10", "1500", 1, BindingLimit.ROOF),
    ],
)
def test_consumption_matched_sizing(
    usable_area_m2: str,
    monthly_kwh: str,
    annual_yield: str,
    panels: int,
    limit: BindingLimit,
) -> None:
    quote = build(
        usable_area_m2=usable_area_m2,
        monthly_consumption_kwh=monthly_kwh,
        annual_yield=annual_yield,
    )

    assert len(quote.system_options) == 1
    option = quote.system_options[0]
    assert option.strategy is SizingStrategy.CONSUMPTION_MATCHED
    assert option.panel_count == panels
    assert option.capacity_kwp == Decimal(panels) * Decimal("0.5")
    assert option.binding_limit is limit


@pytest.mark.parametrize("usable_area_m2", ["2", "2.4", "0.01"])
def test_roof_that_fits_no_panel_is_not_a_viable_system(usable_area_m2: str) -> None:
    with pytest.raises(NoViableSystemError):
        build(usable_area_m2=usable_area_m2)


def test_production_is_capacity_times_specific_yield() -> None:
    option = build().system_options[0]  # 8 panels = 4.0 kWp

    assert option.annual_production_kwh == Decimal("6000")
    assert option.monthly_production_kwh == tuple(
        Decimal(kwh) for kwh in (280, 360, 480, 560, 640, 700, 740, 680, 560, 440, 320, 240)
    )


def test_flat_roof_uses_its_coverage_ratio_and_the_installer_orientation() -> None:
    request = make_request(
        roof_type=RoofType.FLAT, monthly_consumption_kwh="2000", azimuth_deg="90", tilt_deg="30"
    )
    quote = build_quote(
        request=request,
        specific_yield=make_specific_yield(tilt_deg="18"),
        catalog=make_catalog(),
        assumptions=make_assumptions(flat_roof_tilt_deg="18"),
        pricing=make_pricing_assumptions(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )

    # The consumption target is 32 panels. A flat Roof fits 10, while a pitched one fits 16.
    [option] = quote.system_options
    assert option.panel_count == 10
    assert option.binding_limit is BindingLimit.ROOF
    recorded = quote.assumptions
    assert recorded.roof_type is RoofType.FLAT
    assert recorded.coverage_ratio == Decimal("0.50")
    assert recorded.effective_azimuth_deg == Decimal("180")
    assert recorded.effective_tilt_deg == Decimal("18")
    assert recorded.submitted_request.site.roof.azimuth_deg is None
    assert recorded.submitted_request.site.roof.tilt_deg is None


def test_quote_carries_customer_date_and_the_assumptions_it_was_built_with() -> None:
    request = make_request()
    quote = build_quote(
        request=request,
        specific_yield=make_specific_yield(),
        catalog=make_catalog(),
        assumptions=make_assumptions(pitched_coverage_ratio="0.75", system_loss_percent="12"),
        pricing=make_pricing_assumptions(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )

    assert quote.customer == request.customer
    assert quote.quote_date == QUOTE_DATE
    recorded = quote.assumptions
    assert recorded.submitted_request == request
    assert recorded.pvgis_inputs == make_specific_yield().inputs
    assert recorded.coverage_ratio == Decimal("0.75")
    assert recorded.default_panel == make_catalog().default_panel


def test_quote_carries_its_number_and_is_valid_for_the_validity_period() -> None:
    quote = build_quote(
        request=make_request(),
        specific_yield=make_specific_yield(),
        catalog=make_catalog(),
        assumptions=make_assumptions(),
        pricing=make_pricing_assumptions(validity_period_days=15),
        exchange_rate=make_exchange_rate(),
        quote_date=date(2026, 12, 20),
        quote_number="SQ-2026-000123",
    )

    assert quote.quote_number == "SQ-2026-000123"
    assert quote.valid_until == date(2027, 1, 4)  # 15 days after 2026-12-20, across the new year
    assert quote.assumptions.pricing.validity_period_days == 15


def test_same_inputs_give_an_identical_quote() -> None:
    assert build() == build()
