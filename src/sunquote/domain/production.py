"""Production estimate: the Specific Yield and what a system of a given size produces."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SpecificYieldInputs:
    """What the provider actually asked its source for, kept so the Quote can be reproduced.

    Coordinates are the ones sent after rounding, and `aspect_deg` is the PVGIS convention
    (0 = south, 90 = west, -90 = east), not the compass azimuth.
    """

    source: str
    latitude: Decimal
    longitude: Decimal
    tilt_deg: Decimal
    aspect_deg: Decimal
    system_loss_percent: Decimal


@dataclass(frozen=True, slots=True)
class SpecificYield:
    """Expected production per kWp at a Site, with the 12 monthly values (kWh/kWp)."""

    annual_kwh_per_kwp: Decimal
    monthly_kwh_per_kwp: tuple[Decimal, ...]
    inputs: SpecificYieldInputs

    def __post_init__(self) -> None:
        if self.annual_kwh_per_kwp <= 0:
            raise ValueError("annual specific yield must be positive")
        if len(self.monthly_kwh_per_kwp) != 12:
            raise ValueError("a specific yield needs exactly 12 monthly values")


def annual_production_kwh(capacity_kwp: Decimal, specific_yield: SpecificYield) -> Decimal:
    """Year-1 annual production. The provider's system loss is already in the yield."""
    return capacity_kwp * specific_yield.annual_kwh_per_kwp


def monthly_production_kwh(
    capacity_kwp: Decimal, specific_yield: SpecificYield
) -> tuple[Decimal, ...]:
    return tuple(capacity_kwp * month for month in specific_yield.monthly_kwh_per_kwp)
