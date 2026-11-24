from decimal import Decimal

import pytest

from sunquote.domain.catalog import Catalog
from sunquote.domain.errors import UnsupportedSubscriberGroupError
from sunquote.domain.model import (
    Consumption,
    Coordinates,
    Customer,
    Roof,
    RoofType,
    SubscriberGroup,
)
from sunquote.domain.production import SpecificYield
from tests.factories import make_panel, make_request, make_specific_yield


def roof(**overrides: str) -> Roof:
    fields = {"usable_area_m2": "40", "azimuth_deg": "180", "tilt_deg": "30"} | overrides
    return Roof(roof_type=RoofType.PITCHED, **{k: Decimal(v) for k, v in fields.items()})


@pytest.mark.parametrize(
    "build",
    [
        lambda: Customer(name="  "),
        lambda: Coordinates(latitude=Decimal("90.1"), longitude=Decimal("0")),
        lambda: Coordinates(latitude=Decimal("0"), longitude=Decimal("-180.1")),
        lambda: roof(usable_area_m2="0"),
        lambda: roof(azimuth_deg="360"),
        lambda: roof(azimuth_deg="-1"),
        lambda: roof(tilt_deg="90.1"),
        lambda: Consumption(monthly_consumption_kwh=Decimal("0")),
        lambda: Consumption(),
        lambda: Consumption(monthly_bill_try=Decimal("-1")),
        lambda: SpecificYield(
            annual_kwh_per_kwp=Decimal("0"),
            monthly_kwh_per_kwp=make_specific_yield().monthly_kwh_per_kwp,
            inputs=make_specific_yield().inputs,
        ),
        lambda: SpecificYield(
            annual_kwh_per_kwp=Decimal("1500"),
            monthly_kwh_per_kwp=(Decimal("1"),) * 11,
            inputs=make_specific_yield().inputs,
        ),
        lambda: Catalog(panels=(make_panel(),), default_panel_id="missing", inverters=()),
    ],
)
def test_invalid_domain_objects_are_rejected(build: object) -> None:
    with pytest.raises(ValueError):
        build()  # type: ignore[operator]


def test_a_flat_roof_keeps_the_angles_it_was_given_and_does_not_need_them() -> None:
    given = Roof(
        roof_type=RoofType.FLAT,
        usable_area_m2=Decimal(20),
        azimuth_deg=Decimal(90),
        tilt_deg=Decimal(30),
    )
    absent = Roof(roof_type=RoofType.FLAT, usable_area_m2=Decimal(20))

    assert (given.azimuth_deg, given.tilt_deg) == (Decimal(90), Decimal(30))
    assert (absent.azimuth_deg, absent.tilt_deg) == (None, None)
    # What the panels face is the Installer's, whatever was given.
    assert given.effective_orientation(Decimal(15)) == (Decimal(180), Decimal(15))
    assert absent.effective_orientation(Decimal(15)) == (Decimal(180), Decimal(15))


@pytest.mark.parametrize(("azimuth_deg", "tilt_deg"), [("360", None), (None, "91"), ("-1", "0")])
def test_a_flat_roof_rejects_angles_that_are_given_out_of_range(
    azimuth_deg: str | None, tilt_deg: str | None
) -> None:
    with pytest.raises(ValueError, match="deg"):
        Roof(
            roof_type=RoofType.FLAT,
            usable_area_m2=Decimal(20),
            azimuth_deg=None if azimuth_deg is None else Decimal(azimuth_deg),
            tilt_deg=None if tilt_deg is None else Decimal(tilt_deg),
        )


def test_boundary_values_are_accepted() -> None:
    roof(azimuth_deg="0", tilt_deg="0")
    roof(azimuth_deg="359.99", tilt_deg="90")
    Coordinates(latitude=Decimal("-90"), longitude=Decimal("180"))


def test_panel_derives_capacity_and_area_from_datasheet_values() -> None:
    panel = make_panel()  # 500 W, 2000 x 1000 mm

    assert panel.capacity_kwp == Decimal("0.5")
    assert panel.area_m2 == Decimal("2")


def test_residential_is_the_only_supported_subscriber_group() -> None:
    assert SubscriberGroup.parse("residential") is SubscriberGroup.RESIDENTIAL
    with pytest.raises(UnsupportedSubscriberGroupError):
        SubscriberGroup.parse("commercial")


@pytest.mark.parametrize("contracted_power_kw", ["0", "-1"])
def test_a_request_rejects_a_non_positive_contracted_power(contracted_power_kw: str) -> None:
    with pytest.raises(ValueError, match="contracted_power_kw"):
        make_request(contracted_power_kw=contracted_power_kw)
