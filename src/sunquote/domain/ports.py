"""Interfaces to everything outside the domain. Adapters implement them; tests use fakes."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sunquote.domain.model import Coordinates
from sunquote.domain.production import SpecificYield


@dataclass(frozen=True, slots=True)
class SpecificYieldQuery:
    """What to estimate: where, and for which orientation. `azimuth_deg` is a compass bearing."""

    coordinates: Coordinates
    tilt_deg: Decimal
    azimuth_deg: Decimal
    system_loss_percent: Decimal


class SpecificYieldProvider(Protocol):
    async def fetch(self, query: SpecificYieldQuery) -> SpecificYield:
        """Raises `UpstreamUnavailableError` when the source cannot give an answer."""
        ...


class Clock(Protocol):
    def today(self) -> date:
        """The date a Quote is issued on."""
        ...
