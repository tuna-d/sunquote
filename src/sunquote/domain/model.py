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
class GeocodingResult:
    display_name: str
    coordinates: Coordinates
    district: str | None = None
    province: str | None = None


@dataclass(frozen=True, slots=True)
class Roof:
    """A single roof surface. `azimuth_deg` is a compass bearing: 180 is south.

    A pitched Roof needs both angles. A flat Roof does not: the panels sit on racks at the
    Installer's tilt facing south (`effective_orientation`), whatever angles were given. Angles
    that were given stay as submitted, so the Quote records the input unchanged.
    """

    roof_type: RoofType
    usable_area_m2: Decimal
    azimuth_deg: Decimal | None = None
    tilt_deg: Decimal | None = None

    def __post_init__(self) -> None:
        if self.usable_area_m2 <= 0:
            raise ValueError("usable_area_m2 must be positive")
        angles_required = self.roof_type is RoofType.PITCHED
        azimuth, tilt = self.azimuth_deg, self.tilt_deg
        if azimuth is None:
            if angles_required:
                raise ValueError("azimuth_deg must be within [0, 360)")
        elif not Decimal(0) <= azimuth < Decimal(360):
            raise ValueError("azimuth_deg must be within [0, 360)")
        if tilt is None:
            if angles_required:
                raise ValueError("tilt_deg must be within [0, 90]")
        elif not Decimal(0) <= tilt <= Decimal(90):
            raise ValueError("tilt_deg must be within [0, 90]")

    def effective_orientation(self, flat_roof_tilt_deg: Decimal) -> tuple[Decimal, Decimal]:
        """Return the compass azimuth and tilt of the installed panels, in degrees."""
        if self.roof_type is RoofType.FLAT:
            return Decimal(180), flat_roof_tilt_deg
        assert self.azimuth_deg is not None and self.tilt_deg is not None
        return self.azimuth_deg, self.tilt_deg


@dataclass(frozen=True, slots=True)
class Site:
    coordinates: Coordinates | None
    roof: Roof
    address: str | None = None

    def __post_init__(self) -> None:
        if self.coordinates is None and (self.address is None or not self.address.strip()):
            raise ValueError("a site requires an address or coordinates")


@dataclass(frozen=True, slots=True)
class Consumption:
    monthly_consumption_kwh: Decimal | None = None
    monthly_bill_try: Decimal | None = None

    def __post_init__(self) -> None:
        kwh = self.monthly_consumption_kwh
        bill = self.monthly_bill_try
        if kwh is None and bill is None:
            raise ValueError("monthly_consumption_kwh or monthly_bill_try is required")
        if kwh is not None and (not kwh.is_finite() or kwh <= 0):
            raise ValueError("monthly_consumption_kwh must be positive")
        if bill is not None and (not bill.is_finite() or bill <= 0):
            raise ValueError("monthly_bill_try must be positive")


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
