"""The data files are the only place catalog and engineering values live.

These tests read the files that ship with the package, so a typo or a value without a
source fails here and not at startup in front of the interviewer.
"""

import re
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
    load_financial_assumptions,
    load_pricing_assumptions,
    load_residential_tariff,
)
from sunquote.domain.model import RoofType, SubscriberGroup
from sunquote.domain.money import Currency, Money

CATALOG_FILE = default_data_dir() / "catalog.toml"
ASSUMPTIONS_FILE = default_data_dir() / "assumptions.toml"
TARIFF_FILE = default_data_dir() / "tariff.toml"


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
    assert pricing.validity_period_days == 15  # research note section 6


def test_shipped_files_are_marked_placeholder() -> None:
    for path in (CATALOG_FILE, ASSUMPTIONS_FILE, TARIFF_FILE):
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
        data["bos_price_per_kwp"],
        data["labour_price_per_kwp"],
        data["fixed_project_cost"],
        data["margin"],
        data["vat_rate"],
        data["validity_period_days"],
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


def test_every_catalog_price_and_pricing_entry_declares_its_currency() -> None:
    catalog = tomllib.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    assumptions = tomllib.loads(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))

    for item in [*catalog["panels"], *catalog["inverters"]]:
        assert item["price_currency"] in {"USD", "EUR", "TRY"}
    for key in ("bos_price_per_kwp", "labour_price_per_kwp", "fixed_project_cost"):
        assert assumptions[key]["currency"] in {"USD", "EUR", "TRY"}, key


def test_a_catalog_price_takes_the_currency_the_file_declares(tmp_path: Path) -> None:
    data = CATALOG_FILE.read_text(encoding="utf-8").replace(
        'price_currency = "USD"', 'price_currency = "EUR"', 1
    )
    file = tmp_path / "catalog.toml"
    file.write_text(data, encoding="utf-8")

    catalog = load_catalog(file)

    assert catalog.panels[0].unit_price == Money(Decimal(76), Currency.EUR)
    assert catalog.panels[1].unit_price.currency is Currency.USD


@pytest.mark.parametrize("replacement", ["", 'price_currency = "XYZ"'])
def test_a_catalog_price_without_a_known_currency_is_rejected(
    tmp_path: Path, replacement: str
) -> None:
    data = CATALOG_FILE.read_text(encoding="utf-8").replace(
        'price_currency = "USD"', replacement, 1
    )
    file = tmp_path / "catalog.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError, match="price_currency"):
        load_catalog(file)


def test_a_pricing_entry_takes_the_currency_the_file_declares(tmp_path: Path) -> None:
    data = ASSUMPTIONS_FILE.read_text(encoding="utf-8").replace(
        'currency = "USD"', 'currency = "EUR"', 1
    )
    file = tmp_path / "assumptions.toml"
    file.write_text(data, encoding="utf-8")

    pricing = load_pricing_assumptions(file)

    assert pricing.bos_price_per_kwp == Money(Decimal(120), Currency.EUR)
    assert pricing.labour_price_per_kwp.currency is Currency.TRY


def test_a_pricing_entry_without_a_currency_is_rejected(tmp_path: Path) -> None:
    data = ASSUMPTIONS_FILE.read_text(encoding="utf-8").replace('currency = "USD"\n', "", 1)
    file = tmp_path / "assumptions.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValidationError, match="currency"):
        load_pricing_assumptions(file)


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


def test_shipped_tariff_matches_the_research_note() -> None:
    tariff = load_residential_tariff(TARIFF_FILE)

    assert tariff.tier_threshold_kwh_per_year == Decimal(2920)
    assert tariff.low_tariff_try_per_kwh == Decimal("3.24")
    assert tariff.high_tariff_try_per_kwh == Decimal("4.86")
    assert tariff.export_price_try_per_kwh == Decimal("1.24")
    assert tariff.self_consumption_ratio == Decimal("0.85")
    assert tariff.valid_from == date(2026, 4, 4)
    assert "EPDK" in tariff.source


def test_every_tariff_value_names_its_source_kind_and_date() -> None:
    data = tomllib.loads(TARIFF_FILE.read_text(encoding="utf-8"))

    assert data["tariff"]["source"].strip()
    assert isinstance(data["tariff"]["valid_from"], date)
    for key in (
        "tier_threshold_kwh_per_year",
        "low_tariff_try_per_kwh",
        "high_tariff_try_per_kwh",
        "export_price_try_per_kwh",
        "self_consumption_ratio",
    ):
        entry = data[key]
        assert entry["source"].strip(), key
        assert entry["kind"] in {"direct", "derived", "estimate"}, key
        assert isinstance(entry["date"], date), key


def test_a_tariff_whose_low_tier_costs_more_than_the_high_tier_is_rejected(tmp_path: Path) -> None:
    data = TARIFF_FILE.read_text(encoding="utf-8").replace("value = 3.24", "value = 9.99", 1)
    file = tmp_path / "tariff.toml"
    file.write_text(data, encoding="utf-8")

    with pytest.raises(ValueError, match="low Retail Tariff"):
        load_residential_tariff(file)


def test_a_tariff_value_without_a_source_is_rejected(tmp_path: Path) -> None:
    text = TARIFF_FILE.read_text(encoding="utf-8")
    head, _, tail = text.partition("[self_consumption_ratio]")
    tail_without_source = re.sub(r"^source = .*$", "", tail, count=1, flags=re.MULTILINE)
    file = tmp_path / "tariff.toml"
    file.write_text(head + "[self_consumption_ratio]" + tail_without_source, encoding="utf-8")

    with pytest.raises(ValidationError, match="source"):
        load_residential_tariff(file)


def test_shipped_financial_assumptions_match_the_research_note() -> None:
    financial = load_financial_assumptions(ASSUMPTIONS_FILE)

    assert financial.tariff_escalation_rate_real == Decimal("0.02")
    assert financial.equipment_escalation_rate_real == Decimal("0")
    assert financial.lifetime_years == 25
    assert financial.inverter_replacement_year == 12


def test_every_financial_assumption_names_its_source_kind_and_date() -> None:
    data = tomllib.loads(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))

    for key in (
        "tariff_escalation_rate_real",
        "equipment_escalation_rate_real",
        "lifetime_years",
        "inverter_replacement_year",
    ):
        entry = data[key]
        assert entry["source"].strip(), key
        assert entry["kind"] in {"direct", "derived", "estimate"}, key
        assert isinstance(entry["date"], date), key
