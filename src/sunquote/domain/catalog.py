"""The equipment the Installer can install, with datasheet values and unit prices."""

from dataclasses import dataclass
from decimal import Decimal

from sunquote.domain.money import Money


@dataclass(frozen=True, slots=True)
class Panel:
    panel_id: str
    manufacturer: str
    model: str
    power_w: int
    length_mm: int
    width_mm: int
    degradation_rate_per_year: Decimal
    unit_price: Money

    @property
    def capacity_kwp(self) -> Decimal:
        return Decimal(self.power_w) / 1000

    @property
    def area_m2(self) -> Decimal:
        return Decimal(self.length_mm * self.width_mm) / 1_000_000


@dataclass(frozen=True, slots=True)
class Inverter:
    inverter_id: str
    manufacturer: str
    model: str
    ac_power_kw: Decimal
    unit_price: Money

    def __post_init__(self) -> None:
        if self.ac_power_kw <= 0:
            raise ValueError("ac_power_kw must be positive")


@dataclass(frozen=True, slots=True)
class Catalog:
    panels: tuple[Panel, ...]
    default_panel_id: str
    inverters: tuple[Inverter, ...]

    def __post_init__(self) -> None:
        if self.default_panel_id not in {panel.panel_id for panel in self.panels}:
            raise ValueError(f"default panel {self.default_panel_id!r} is not in the catalog")

    @property
    def default_panel(self) -> Panel:
        return next(panel for panel in self.panels if panel.panel_id == self.default_panel_id)
