"""The inputs of a quote request, as the domain understands them.

These are plain frozen dataclasses. The API layer validates raw JSON with Pydantic and builds
these; the checks here are the domain's own invariants, a second line of defence.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sunquote.domain.errors import UnsupportedSubscriberGroupError


class RoofType(StrEnum):
    PITCHED = "pitched"
    FLAT = "flat"


class SubscriberGroup(StrEnum):
    """Only residential is priced for now; the enum is where commercial would be added."""

    RESIDENTIAL = "residential"

    @classmethod
    def parse(cls, value: str) -> "SubscriberGroup":
        try:
            return cls(value)
        except ValueError:
            raise UnsupportedSubscriberGroupError(value, tuple(cls)) from None


@dataclass(frozen=True, slots=True)
class Customer:
    name: str
    phone: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("customer name must not be blank")


@dataclass(frozen=True, slots=True)
class Coordinates:
    latitude: Decimal
    longitude: Decimal

    def __post_init__(self) -> None:
        if not Decimal(-90) <= self.latitude <= Decimal(90):
            raise ValueError("latitude must be within [-90, 90]")
        if not Decimal(-180) <= self.longitude <= Decimal(180):
            raise ValueError("longitude must be within [-180, 180]")


@dataclass(frozen=True, slots=True)
class Roof:
    """A single roof surface. `azimuth_deg` is a compass bearing: 180 is south."""

    roof_type: RoofType
    usable_area_m2: Decimal
    azimuth_deg: Decimal | None = None
    tilt_deg: Decimal | None = None

    def __post_init__(self) -> None:
        if self.usable_area_m2 <= 0:
            raise ValueError("usable_area_m2 must be positive")
        if self.roof_type is RoofType.FLAT:
            object.__setattr__(self, "azimuth_deg", None)
            object.__setattr__(self, "tilt_deg", None)
            return
        if self.azimuth_deg is None or not Decimal(0) <= self.azimuth_deg < Decimal(360):
            raise ValueError("azimuth_deg must be within [0, 360)")
        if self.tilt_deg is None or not Decimal(0) <= self.tilt_deg <= Decimal(90):
            raise ValueError("tilt_deg must be within [0, 90]")

    def effective_orientation(self, flat_roof_tilt_deg: Decimal) -> tuple[Decimal, Decimal]:
        """Return the compass azimuth and tilt of the installed panels, in degrees."""
        if self.roof_type is RoofType.FLAT:
            return Decimal(180), flat_roof_tilt_deg
        assert self.azimuth_deg is not None and self.tilt_deg is not None
        return self.azimuth_deg, self.tilt_deg


@dataclass(frozen=True, slots=True)
class Site:
    coordinates: Coordinates
    roof: Roof


@dataclass(frozen=True, slots=True)
class Consumption:
    monthly_consumption_kwh: Decimal

    def __post_init__(self) -> None:
        if self.monthly_consumption_kwh <= 0:
            raise ValueError("monthly_consumption_kwh must be positive")


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    customer: Customer
    site: Site
    consumption: Consumption
    subscriber_group: SubscriberGroup
    # The Site's grid connection power, when the Sales Rep knows it; absent means the default.
    contracted_power_kw: Decimal | None = None

    def __post_init__(self) -> None:
        if self.contracted_power_kw is not None and self.contracted_power_kw <= 0:
            raise ValueError("contracted_power_kw must be positive")
