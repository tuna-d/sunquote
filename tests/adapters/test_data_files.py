"""The data files are the only place catalog and engineering values live.

These tests read the files that ship with the package, so a typo or a value without a
source fails here and not at startup in front of the interviewer.
"""

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from sunquote.adapters.data_files import (
    default_data_dir,
    load_catalog,
    load_engineering_assumptions,
    load_pricing_assumptions,
)
from sunquote.domain.model import RoofType, SubscriberGroup
from sunquote.domain.money import Currency, Money

CATALOG_FILE = default_data_dir() / "catalog.toml"
ASSUMPTIONS_FILE = default_data_dir() / "assumptions.toml"


def test_shipped_catalog_has_the_default_panel_from_the_research_note() -> None:
    catalog = load_catalog(CATALOG_FILE)

    panel = catalog.default_panel
    assert panel.manufacturer == "Trina Solar"
    assert panel.power_w == 440
    assert (panel.length_mm, panel.width_mm) == (1762, 1134)
    assert panel.area_m2 == Decimal("1.998108")
    assert panel.capacity_kwp == Decimal("0.44")
    assert panel.degradation_rate_per_year == Decimal("0.0047")
    assert panel.unit_price == Money(Decimal(76), Currency.USD)  # research note section 2.3


def test_shipped_catalog_has_the_huawei_inverter_family_priced_in_usd() -> None:
    inverters = load_catalog(CATALOG_FILE).inverters

    assert [(i.model, i.ac_power_kw, i.unit_price.amount) for i in inverters] == [
        ("SUN2000-3KTL-M1", Decimal(3), Decimal(650)),
        ("SUN2000-4KTL-M1", Decimal(4), Decimal(725)),
        ("SUN2000-5KTL-M1", Decimal(5), Decimal(800)),
        ("SUN2000-6KTL-M1", Decimal(6), Decimal(900)),
        ("SUN2000-8KTL-M1", Decimal(8), Decimal(1050)),
        ("SUN2000-10KTL-M1", Decimal(10), Decimal(1200)),
    ]
    assert {i.unit_price.currency for i in inverters} == {Currency.USD}


def test_shipped_assumptions_hold_coverage_ratios_flat_roof_tilt_and_system_loss() -> None:
    assumptions = load_engineering_assumptions(ASSUMPTIONS_FILE)

    assert assumptions.coverage_ratio(RoofType.PITCHED) == Decimal("0.80")
    assert assumptions.coverage_ratio(RoofType.FLAT) == Decimal("0.50")
    assert assumptions.flat_roof_tilt_deg == Decimal("15")
    assert assumptions.system_loss_percent == Decimal("14")


def test_shipped_catalog_leaves_no_sizing_gap_from_3_kwp_to_the_largest_inverters_reach() -> None:
    """A system of any panel count in that span has a compatible inverter.

    Below 3 kWp the smallest inverter is oversized, and above the 10 kW inverter's maximum
    ratio nothing fits (the Contracted Power cap keeps residential systems below that).
    """
    catalog = load_catalog(CATALOG_FILE)
    ratio_range = load_engineering_assumptions(ASSUMPTIONS_FILE).dc_ac_ratio_range
    panel_kwp = catalog.default_panel.capacity_kwp
    reach_kwp = max(i.ac_power_kw for i in catalog.inverters) * ratio_range.maximum

    spanned = [n * panel_kwp for n in range(1, 100) if 3 <= n * panel_kwp <= reach_kwp]
    uncovered = [
        kwp
        for kwp in spanned
        if not any(ratio_range.contains(kwp / i.ac_power_kw) for i in catalog.inverters)
    ]

    assert spanned
    assert uncovered == []


def test_shipped_assumptions_hold_the_dc_ac_range() -> None:
    ratio_range = load_engineering_assumptions(ASSUMPTIONS_FILE).dc_ac_ratio_range

    assert (ratio_range.minimum, ratio_range.maximum) == (Decimal("1.00"), Decimal("1.50"))


def test_shipped_assumptions_default_the_residential_contracted_power_to_10_kw() -> None:
    assumptions = load_engineering_assumptions(ASSUMPTIONS_FILE)

    assert assumptions.default_contracted_power_kw(SubscriberGroup.RESIDENTIAL) == Decimal(10)


def test_shipped_pricing_assumptions_match_the_research_note() -> None:
    pricing = load_pricing_assumptions(ASSUMPTIONS_FILE)

    assert pricing.bos_price_per_kwp == Money(Decimal(120), Currency.USD)
    assert pricing.labour_price_per_kwp == Money(Decimal(4000), Currency.TRY)
    assert pricing.fixed_project_cost == Money(Decimal(20000), Currency.TRY)
    assert pricing.margin == Decimal("0.25")
    assert pricing.vat_rate == Decimal("0.20")


def test_shipped_files_are_marked_placeholder() -> None:
    for path in (CATALOG_FILE, ASSUMPTIONS_FILE):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["meta"]["placeholder"] is True, path.name


def test_every_assumption_value_names_its_source_kind_and_date() -> None:
    data = tomllib.loads(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))

    values = [
        data["system_loss_percent"],
        data["flat_roof_tilt_deg"],
        *data["coverage_ratio"].values(),
        data["dc_ac_ratio_min"],
        data["dc_ac_ratio_max"],
        data["default_contracted_power_kw"]["residential"],
        data["bos_usd_per_kwp"],
        data["labour_try_per_kwp"],
        data["fixed_project_cost_try"],
        data["margin"],
        data["vat_rate"],
    ]
    for entry in values:
        assert entry["source"].strip()
        assert entry["kind"] in {"direct", "derived", "estimate"}
        assert isinstance(entry["date"], date)


def test_every_panel_names_its_datasheet_source_and_date() -> None:
    data = tomllib.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    for item in [*data["panels"], *data["inverters"]]:
        assert item["source"].startswith("https://")
        assert isinstance(item["source_date"], date)


def test_every_catalog_unit_price_is_an_estimate_with_its_own_source_and_date() -> None:
    data = tomllib.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    for item in [*data["panels"], *data["inverters"]]:
        assert item["price_kind"] in {"direct", "derived", "estimate"}
        assert item["price_source"].strip()
        assert isinstance(item["price_date"], date)


def test_a_value_without_a_source_is_rejected(tmp_path: Path) -> None:
    file = tmp_path / "assumptions.toml"
    file.write_text(
        """
[meta]
placeholder = true
description = "test"

[coverage_ratio.pitched]
value = 0.8
kind = "estimate"
date = 2026-11-24

[system_loss_percent]
value = 14
kind = "direct"
source = "test"
date = 2026-11-24
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="source"):
        load_engineering_assumptions(file)


def test_a_default_panel_missing_from_the_catalog_is_rejected(tmp_path: Path) -> None:
    data = CATALOG_FILE.read_text(encoding="utf-8").replace(
        'default_panel = "', 'default_panel = "no-such-panel-', 1
    )
    file = tmp_path / "catalog.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValueError, match="no-such-panel"):
        load_catalog(file)


def test_ratios_outside_their_range_are_rejected(tmp_path: Path) -> None:
    data = ASSUMPTIONS_FILE.read_text(encoding="utf-8").replace("value = 0.80", "value = 1.5", 1)
    file = tmp_path / "assumptions.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_engineering_assumptions(file)


def test_a_catalog_price_in_another_currency_than_usd_is_rejected(tmp_path: Path) -> None:
    data = CATALOG_FILE.read_text(encoding="utf-8").replace("unit_price_usd", "unit_price_eur", 1)
    file = tmp_path / "catalog.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError, match="unit_price"):
        load_catalog(file)


def test_an_inverter_without_ac_power_is_rejected(tmp_path: Path) -> None:
    data = CATALOG_FILE.read_text(encoding="utf-8").replace(
        "ac_power_kw = 3\n", "ac_power_kw = 0\n", 1
    )
    file = tmp_path / "catalog.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError, match="ac_power_kw"):
        load_catalog(file)


def test_a_dc_ac_range_with_minimum_above_maximum_is_rejected(tmp_path: Path) -> None:
    data = ASSUMPTIONS_FILE.read_text(encoding="utf-8").replace("value = 1.00", "value = 1.60", 1)
    file = tmp_path / "assumptions.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValueError, match="DC/AC"):
        load_engineering_assumptions(file)


def test_a_negative_margin_is_rejected(tmp_path: Path) -> None:
    data = ASSUMPTIONS_FILE.read_text(encoding="utf-8")
    data = data.replace("[margin]\nvalue = 0.25", "[margin]\nvalue = -0.25")
    assert data != ASSUMPTIONS_FILE.read_text(encoding="utf-8")
    file = tmp_path / "assumptions.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError, match="margin"):
        load_pricing_assumptions(file)
