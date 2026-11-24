"""The PVGIS adapter against recorded responses (no network).

The real call is in `test_pvgis_integration.py`.
"""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from sunquote.adapters.pvgis import PvgisSpecificYieldProvider
from sunquote.domain.errors import UpstreamUnavailableError
from sunquote.domain.model import Coordinates
from sunquote.domain.ports import SpecificYieldQuery

pytestmark = pytest.mark.anyio

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://pvgis.example/api/v5_3"


def recording(name: str) -> str:
    return (RECORDINGS / name).read_text(encoding="utf-8")


def make_query(
    *,
    latitude: str = "39.9334",
    longitude: str = "32.8597",
    tilt_deg: str = "30",
    azimuth_deg: str = "180",
    system_loss_percent: str = "14",
) -> SpecificYieldQuery:
    return SpecificYieldQuery(
        coordinates=Coordinates(latitude=Decimal(latitude), longitude=Decimal(longitude)),
        tilt_deg=Decimal(tilt_deg),
        azimuth_deg=Decimal(azimuth_deg),
        system_loss_percent=Decimal(system_loss_percent),
    )


def provider_with(transport: httpx.MockTransport) -> PvgisSpecificYieldProvider:
    return PvgisSpecificYieldProvider(
        client=httpx.AsyncClient(transport=transport), base_url=BASE_URL, timeout_seconds=5.0
    )


def respond_with(body: str, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, text=body))


def capturing(body: str) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler), seen


async def test_parses_annual_and_monthly_specific_yield() -> None:
    provider = provider_with(respond_with(recording("pvgis_pvcalc_ankara.json")))

    result = await provider.fetch(make_query())

    assert result.annual_kwh_per_kwp == Decimal("1472.13")
    assert len(result.monthly_kwh_per_kwp) == 12
    assert result.monthly_kwh_per_kwp[0] == Decimal("69.17")
    assert result.monthly_kwh_per_kwp[1] == Decimal("87.31")


async def test_sends_peakpower_one_loss_tilt_and_rounded_coordinates() -> None:
    transport, seen = capturing(recording("pvgis_pvcalc_ankara.json"))

    await provider_with(transport).fetch(
        make_query(
            latitude="39.93349", longitude="32.8595", tilt_deg="25", system_loss_percent="12"
        )
    )

    [request] = seen
    assert request.url.path == "/api/v5_3/PVcalc"
    assert dict(request.url.params) == {
        "lat": "39.933",
        "lon": "32.860",  # 32.8595 rounds half-up to 32.860
        "peakpower": "1",
        "loss": "12",
        "angle": "25",
        "aspect": "0",
        "outputformat": "json",
    }


@pytest.mark.parametrize(
    ("azimuth_deg", "aspect"),
    [("180", "0"), ("270", "90"), ("90", "-90"), ("225", "45"), ("0", "-180"), ("359", "179")],
)
async def test_aspect_is_compass_azimuth_minus_180(azimuth_deg: str, aspect: str) -> None:
    transport, seen = capturing(recording("pvgis_pvcalc_ankara.json"))

    result = await provider_with(transport).fetch(make_query(azimuth_deg=azimuth_deg))

    assert seen[0].url.params["aspect"] == aspect
    assert result.inputs.aspect_deg == Decimal(aspect)


async def test_reports_the_inputs_it_actually_sent() -> None:
    provider = provider_with(respond_with(recording("pvgis_pvcalc_ankara.json")))

    result = await provider.fetch(make_query(latitude="39.93349", longitude="32.8595"))

    inputs = result.inputs
    assert inputs.latitude == Decimal("39.933")
    assert inputs.longitude == Decimal("32.860")
    assert inputs.tilt_deg == Decimal("30")
    assert inputs.aspect_deg == Decimal("0")
    assert inputs.system_loss_percent == Decimal("14")
    assert inputs.source == f"{BASE_URL}/PVcalc"


async def test_timeout_is_upstream_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(UpstreamUnavailableError) as raised:
        await provider_with(httpx.MockTransport(handler)).fetch(make_query())

    assert raised.value.service == "PVGIS"


async def test_connection_failure_is_upstream_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(UpstreamUnavailableError):
        await provider_with(httpx.MockTransport(handler)).fetch(make_query())


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_server_errors_are_upstream_unavailable(status: int) -> None:
    with pytest.raises(UpstreamUnavailableError):
        await provider_with(respond_with("busy", status)).fetch(make_query())


async def test_location_over_the_sea_is_upstream_unavailable_with_pvgis_message() -> None:
    provider = provider_with(respond_with(recording("pvgis_pvcalc_over_sea.json"), status=400))

    with pytest.raises(UpstreamUnavailableError, match="Location over the sea"):
        await provider.fetch(make_query(latitude="36", longitude="30"))


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "{}",
        json.dumps({"outputs": {"totals": {"fixed": {"E_y": 1472.13}}, "monthly": {"fixed": []}}}),
        json.dumps({"outputs": {"totals": {"fixed": {"E_y": "n/a"}}, "monthly": {"fixed": []}}}),
    ],
)
async def test_malformed_response_is_upstream_unavailable(body: str) -> None:
    with pytest.raises(UpstreamUnavailableError):
        await provider_with(respond_with(body)).fetch(make_query())
