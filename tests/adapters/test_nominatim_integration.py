"""One real call for a public landmark, run with `uv run pytest -m integration`."""

from decimal import Decimal

import httpx
import pytest

from sunquote.adapters.nominatim import NominatimGeocoder
from sunquote.config import Settings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_real_nominatim_resolves_a_landmark_in_ankara() -> None:
    settings = Settings()
    async with httpx.AsyncClient() as client:
        result = await NominatimGeocoder(
            client=client,
            base_url=settings.nominatim_base_url,
            timeout_seconds=settings.nominatim_timeout_seconds,
        ).geocode("An\u0131tkabir, Ankara")

    assert "An\u0131tkabir" in result.display_name
    assert Decimal("39.9") < result.coordinates.latitude < Decimal("40")
    assert Decimal("32.8") < result.coordinates.longitude < Decimal("32.9")
    assert (result.district, result.province) == ("Çankaya", "Ankara")
