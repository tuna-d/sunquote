"""Loaders for the placeholder data files (catalog, engineering and pricing assumptions).

The files are TOML so they can carry comments. Floats are parsed straight into `Decimal`
(never through `float`). Pydantic validates each file, including that every value names its
kind, source and date; the loaders then hand the domain plain dataclasses.
"""

import tomllib
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sunquote.domain.assumptions import (
    DcAcRatioRange,
    EngineeringAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog, Inverter, Panel
from sunquote.domain.model import RoofType
from sunquote.domain.money import Currency, Money

Kind = Literal["direct", "derived", "estimate"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Meta(_Strict):
    placeholder: Literal[True]
    description: str


class _SourcedValue(_Strict):
    value: Decimal
    kind: Kind
    source: str = Field(min_length=1)
    date: date


class _Ratio(_SourcedValue):
    value: Decimal = Field(gt=0, le=1)


class _Tilt(_SourcedValue):
    value: Decimal = Field(ge=0, le=90)


class _Percent(_SourcedValue):
    value: Decimal = Field(ge=0, lt=100)


class _Positive(_SourcedValue):
    value: Decimal = Field(gt=0)


class _Days(_SourcedValue):
    value: int = Field(gt=0)  # type: ignore[assignment]  # a whole number of days, not a Decimal


class _NonNegative(_SourcedValue):
    value: Decimal = Field(ge=0)


class _CatalogItem(_Strict):
    """What panels and inverters share: a datasheet source, and a unit price with its own."""

    manufacturer: str
    model: str
    # Catalog prices are USD for now: the quote carries one Exchange Rate (USD/TRY).
    unit_price_usd: Decimal = Field(gt=0)
    price_kind: Kind
    price_source: str = Field(min_length=1)
    price_date: date
    source: str = Field(min_length=1)
    source_date: date
    kind: Kind
    notes: str = ""


class _PanelEntry(_CatalogItem):
    panel_id: str = Field(min_length=1)
    power_w: int = Field(gt=0)
    length_mm: int = Field(gt=0)
    width_mm: int = Field(gt=0)
    degradation_rate_per_year: Decimal = Field(ge=0, lt=1)


class _InverterEntry(_CatalogItem):
    inverter_id: str = Field(min_length=1)
    ac_power_kw: Decimal = Field(gt=0)


class _CatalogFile(_Strict):
    meta: _Meta
    default_panel: str
    panels: list[_PanelEntry] = Field(min_length=1)
    inverters: list[_InverterEntry] = Field(min_length=1)


class _CoverageRatios(_Strict):
    pitched: _Ratio
    flat: _Ratio


class _AssumptionsFile(_Strict):
    meta: _Meta
    coverage_ratio: _CoverageRatios
    system_loss_percent: _Percent
    dc_ac_ratio_min: _Positive
    dc_ac_ratio_max: _Positive
    bos_usd_per_kwp: _Positive
    labour_try_per_kwp: _Positive
    fixed_project_cost_try: _NonNegative
    margin: _NonNegative
    vat_rate: _NonNegative
    validity_period_days: _Days
    flat_roof_tilt_deg: _Tilt


def default_data_dir() -> Path:
    """The data files that ship inside the package."""
    return Path(str(resources.files("sunquote") / "data"))


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file, parse_float=Decimal)


def load_catalog(path: Path) -> Catalog:
    file = _CatalogFile.model_validate(_read(path))
    return Catalog(
        panels=tuple(
            Panel(
                panel_id=entry.panel_id,
                manufacturer=entry.manufacturer,
                model=entry.model,
                power_w=entry.power_w,
                length_mm=entry.length_mm,
                width_mm=entry.width_mm,
                degradation_rate_per_year=entry.degradation_rate_per_year,
                unit_price=Money(entry.unit_price_usd, Currency.USD),
            )
            for entry in file.panels
        ),
        default_panel_id=file.default_panel,
        inverters=tuple(
            Inverter(
                inverter_id=entry.inverter_id,
                manufacturer=entry.manufacturer,
                model=entry.model,
                ac_power_kw=entry.ac_power_kw,
                unit_price=Money(entry.unit_price_usd, Currency.USD),
            )
            for entry in file.inverters
        ),
    )


def load_engineering_assumptions(path: Path) -> EngineeringAssumptions:
    file = _AssumptionsFile.model_validate(_read(path))
    return EngineeringAssumptions(
        coverage_ratio_by_roof_type={
            RoofType.PITCHED: file.coverage_ratio.pitched.value,
            RoofType.FLAT: file.coverage_ratio.flat.value,
        },
        system_loss_percent=file.system_loss_percent.value,
        dc_ac_ratio_range=DcAcRatioRange(
            minimum=file.dc_ac_ratio_min.value, maximum=file.dc_ac_ratio_max.value
        ),
        flat_roof_tilt_deg=file.flat_roof_tilt_deg.value,
    )


def load_pricing_assumptions(path: Path) -> PricingAssumptions:
    file = _AssumptionsFile.model_validate(_read(path))
    return PricingAssumptions(
        bos_price_per_kwp=Money(file.bos_usd_per_kwp.value, Currency.USD),
        labour_price_per_kwp=Money(file.labour_try_per_kwp.value, Currency.TRY),
        fixed_project_cost=Money(file.fixed_project_cost_try.value, Currency.TRY),
        margin=file.margin.value,
        vat_rate=file.vat_rate.value,
        validity_period_days=file.validity_period_days.value,
    )
