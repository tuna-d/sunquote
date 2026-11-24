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
)
from sunquote.domain.model import RoofType

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


def test_shipped_assumptions_hold_coverage_ratios_flat_roof_tilt_and_system_loss() -> None:
    assumptions = load_engineering_assumptions(ASSUMPTIONS_FILE)

    assert assumptions.coverage_ratio(RoofType.PITCHED) == Decimal("0.80")
    assert assumptions.coverage_ratio(RoofType.FLAT) == Decimal("0.50")
    assert assumptions.flat_roof_tilt_deg == Decimal("15")
    assert assumptions.system_loss_percent == Decimal("14")


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
    ]
    for entry in values:
        assert entry["source"].strip()
        assert entry["kind"] in {"direct", "derived", "estimate"}
        assert isinstance(entry["date"], date)


def test_every_panel_names_its_datasheet_source_and_date() -> None:
    data = tomllib.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    for panel in data["panels"]:
        assert panel["source"].startswith("https://")
        assert isinstance(panel["source_date"], date)


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
