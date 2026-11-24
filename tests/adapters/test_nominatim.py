import asyncio
import json
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from time import monotonic

import httpx
import pytest

from sunquote.adapters.nominatim import NominatimGeocoder
from sunquote.domain.errors import AddressNotFoundError, UpstreamUnavailableError
from sunquote.domain.model import Coordinates

pytestmark = pytest.mark.anyio

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://nominatim.example"
ADDRESS = "An\u0131tkabir, Ankara"


def recording(name: str) -> str:
    return (RECORDINGS / f"nominatim_{name}.json").read_text(encoding="utf-8")


async def test_requests_one_turkish_match_and_parses_the_recorded_result() -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert dict(request.url.params) == {
            "q": ADDRESS,
            "format": "jsonv2",
            "countrycodes": "tr",
            "limit": "1",
            "addressdetails": "1",
        }
        assert request.headers["User-Agent"] == "sunquote"
        assert request.extensions["timeout"]["read"] == 5.0
        return httpx.Response(200, text=recording("ankara"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        result = await NominatimGeocoder(
            client=client, base_url=BASE_URL, timeout_seconds=5.0
        ).geocode(ADDRESS)

    assert result.display_name == (
        "An\u0131tkabir, 31, Akdeniz Caddesi, Mebusevleri Mahallesi, Ankara, "
        "Çankaya, Ankara, İç Anadolu Bölgesi, 06570, Türkiye"
    )
    assert result.coordinates == Coordinates(Decimal("39.9267385"), Decimal("32.8365635"))
    assert (result.district, result.province) == ("Çankaya", "Ankara")


@pytest.mark.parametrize(
    ("remove", "district", "province"),
    [
        (("town",), "County", "Ankara"),
        (("town", "county", "province"), "City district", "State"),
        (("town", "county", "city_district", "province"), "Mebusevleri Mahallesi", "State"),
    ],
)
async def test_uses_the_first_available_district_and_province_components(
    remove: tuple[str, ...], district: str, province: str
) -> None:
    # Keep the recorded match and vary its address components to cover alternate OSM tags.
    [match] = json.loads(recording("ankara"))
    match["address"].update(county="County", city_district="City district", state="State")
    for key in remove:
        del match["address"][key]
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=[match]))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await NominatimGeocoder(
            client=client, base_url=BASE_URL, timeout_seconds=5.0
        ).geocode(ADDRESS)

    assert (result.district, result.province) == (district, province)


async def test_a_match_without_district_still_provides_the_province() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=recording("mardin")))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await NominatimGeocoder(
            client=client, base_url=BASE_URL, timeout_seconds=5.0
        ).geocode("Mardin")

    assert (result.district, result.province) == (None, "Mardin")


async def test_concurrent_geocoders_share_the_one_request_per_second_limit() -> None:
    arrival_times: list[float] = []

    def upstream(_: httpx.Request) -> httpx.Response:
        arrival_times.append(monotonic())
        return httpx.Response(200, text=recording("ankara"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        geocoders = [
            NominatimGeocoder(client=client, base_url=BASE_URL, timeout_seconds=5.0)
            for _ in range(2)
        ]
        await asyncio.gather(*(geocoder.geocode(ADDRESS) for geocoder in geocoders))

    assert len(arrival_times) == 2
    assert all(later - earlier >= 0.99 for earlier, later in pairwise(arrival_times))


async def test_an_empty_result_is_address_not_found() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=recording("not_found")))
    async with httpx.AsyncClient(transport=transport) as client:
        geocoder = NominatimGeocoder(client=client, base_url=BASE_URL, timeout_seconds=5.0)
        with pytest.raises(AddressNotFoundError):
            await geocoder.geocode("sunquote-test-nonexistent-765c188d")


async def test_a_timeout_is_upstream_unavailable() -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("unreachable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        geocoder = NominatimGeocoder(client=client, base_url=BASE_URL, timeout_seconds=5.0)
        with pytest.raises(UpstreamUnavailableError, match=r"Nominatim.*timed out"):
            await geocoder.geocode(ADDRESS)
