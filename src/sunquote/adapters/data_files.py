"""Loaders for the placeholder data files (catalog, tariff, engineering, pricing and financial
assumptions).

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
    FinancialAssumptions,
    PricingAssumptions,
)
from sunquote.domain.catalog import Catalog, Inverter, Panel
from sunquote.domain.model import RoofType, SubscriberGroup
from sunquote.domain.money import Currency, Money
from sunquote.domain.tariff import ResidentialTariff

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


class _PositivePrice(_Positive):
    """A price: the value in the currency the file declares for it."""

    currency: Currency


class _Days(_SourcedValue):
    value: int = Field(gt=0)  # type: ignore[assignment]  # a whole number of days, not a Decimal


class _NonNegative(_SourcedValue):
    value: Decimal = Field(ge=0)


class _NonNegativePrice(_NonNegative):
    currency: Currency


class _Share(_SourcedValue):
    value: Decimal = Field(ge=0, le=1)


class _Rate(_SourcedValue):
    """A yearly rate as a share (0.02 is 2%); it may be negative but not below -100%."""

    value: Decimal = Field(gt=-1)


class _PositiveYears(_Strict):
    value: int = Field(ge=1)
    kind: Kind
    source: str = Field(min_length=1)
    date: date


class _CatalogItem(_Strict):
    """What panels and inverters share: a datasheet source, and a unit price with its own."""

    manufacturer: str
    model: str
    unit_price: Decimal = Field(gt=0)
    price_currency: Currency
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


class _DefaultContractedPower(_Strict):
    residential: _Positive


class _AssumptionsFile(_Strict):
    meta: _Meta
    coverage_ratio: _CoverageRatios
    system_loss_percent: _Percent
    dc_ac_ratio_min: _Positive
    dc_ac_ratio_max: _Positive
    bos_price_per_kwp: _PositivePrice
    labour_price_per_kwp: _PositivePrice
    fixed_project_cost: _NonNegativePrice
    margin: _NonNegative
    vat_rate: _NonNegative
    validity_period_days: _Days
    flat_roof_tilt_deg: _Tilt
    default_contracted_power_kw: _DefaultContractedPower
    tariff_escalation_rate_real: _Rate
    equipment_escalation_rate_real: _Rate
    lifetime_years: _PositiveYears
    inverter_replacement_year: _PositiveYears


class _TariffMeta(_Strict):
    valid_from: date
    source: str = Field(min_length=1)


class _TariffFile(_Strict):
    meta: _Meta
    tariff: _TariffMeta
    tier_threshold_kwh_per_year: _Positive
    low_tariff_try_per_kwh: _Positive
    high_tariff_try_per_kwh: _Positive
    export_price_try_per_kwh: _NonNegative
    self_consumption_ratio: _Share


def default_data_dir() -> Path:
    """The data files that ship inside the package."""
    return Path(str(resources.files("sunquote") / "data"))


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file, parse_float=Decimal)


def _money(price: _PositivePrice | _NonNegativePrice) -> Money:
    return Money(price.value, price.currency)


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
                unit_price=Money(entry.unit_price, entry.price_currency),
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
                unit_price=Money(entry.unit_price, entry.price_currency),
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
        default_contracted_power_kw_by_subscriber_group={
            SubscriberGroup.RESIDENTIAL: file.default_contracted_power_kw.residential.value
        },
    )


def load_pricing_assumptions(path: Path) -> PricingAssumptions:
    file = _AssumptionsFile.model_validate(_read(path))
    return PricingAssumptions(
        bos_price_per_kwp=_money(file.bos_price_per_kwp),
        labour_price_per_kwp=_money(file.labour_price_per_kwp),
        fixed_project_cost=_money(file.fixed_project_cost),
        margin=file.margin.value,
        vat_rate=file.vat_rate.value,
        validity_period_days=file.validity_period_days.value,
    )


def load_financial_assumptions(path: Path) -> FinancialAssumptions:
    file = _AssumptionsFile.model_validate(_read(path))
    return FinancialAssumptions(
        tariff_escalation_rate_real=file.tariff_escalation_rate_real.value,
        equipment_escalation_rate_real=file.equipment_escalation_rate_real.value,
        lifetime_years=file.lifetime_years.value,
        inverter_replacement_year=file.inverter_replacement_year.value,
    )


def load_residential_tariff(path: Path) -> ResidentialTariff:
    file = _TariffFile.model_validate(_read(path))
    return ResidentialTariff(
        tier_threshold_kwh_per_year=file.tier_threshold_kwh_per_year.value,
        low_tariff_try_per_kwh=file.low_tariff_try_per_kwh.value,
        high_tariff_try_per_kwh=file.high_tariff_try_per_kwh.value,
        export_price_try_per_kwh=file.export_price_try_per_kwh.value,
        self_consumption_ratio=file.self_consumption_ratio.value,
        valid_from=file.tariff.valid_from,
        source=file.tariff.source,
    )
