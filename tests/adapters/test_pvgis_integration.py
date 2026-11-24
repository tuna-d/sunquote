"""One real call to PVGIS. Run by hand with `uv run pytest -m integration`."""

from decimal import Decimal

import httpx
import pytest

from sunquote.adapters.pvgis import DEFAULT_PVGIS_BASE_URL, PvgisSpecificYieldProvider
from sunquote.domain.model import Coordinates
from sunquote.domain.ports import SpecificYieldQuery

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_real_pvgis_returns_a_plausible_yield_for_ankara() -> None:
    async with httpx.AsyncClient() as client:
        provider = PvgisSpecificYieldProvider(
            client=client, base_url=DEFAULT_PVGIS_BASE_URL, timeout_seconds=30.0
        )
        result = await provider.fetch(
            SpecificYieldQuery(
                coordinates=Coordinates(latitude=Decimal("39.9334"), longitude=Decimal("32.8597")),
                tilt_deg=Decimal("30"),
                azimuth_deg=Decimal("180"),
                system_loss_percent=Decimal("14"),
            )
        )

    # Central Anatolia, south-facing at 30 degrees: roughly 1,400-1,600 kWh/kWp/year.
    assert Decimal("1300") < result.annual_kwh_per_kwp < Decimal("1700")
    assert len(result.monthly_kwh_per_kwp) == 12
    assert result.monthly_kwh_per_kwp[5] > result.monthly_kwh_per_kwp[11]  # June > December
