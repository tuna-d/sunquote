"""The real adapters and shipped data files wired together, with a recorded PVGIS response."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sunquote.adapters.clock import SystemClock
from sunquote.api.app import create_app
from sunquote.bootstrap import build_dependencies
from sunquote.config import Settings
from tests.api.test_quotes import valid_body

RECORDING = Path(__file__).parent / "adapters" / "recordings" / "pvgis_pvcalc_ankara.json"


@pytest.fixture
def requests_seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def wired_client(requests_seen: list[httpx.Request]) -> Iterator[TestClient]:
    def pvgis(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, text=RECORDING.read_text(encoding="utf-8"))

    settings = Settings()
    dependencies = build_dependencies(settings, transport=httpx.MockTransport(pvgis))
    with TestClient(create_app(settings, dependencies)) as client:
        yield client


def test_quote_from_shipped_data_files_and_recorded_pvgis_response(
    wired_client: TestClient, requests_seen: list[httpx.Request]
) -> None:
    response = wired_client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    [option] = quote["system_options"]
    # 6000 kWh / 1472.13 kWh/kWp = 4.076 kWp; 4.076 / 0.44 kWp = 9.26 -> 9 panels = 3.96 kWp.
    assert option["panel_count"] == 9
    assert option["capacity_kwp"] == 3.96
    assert option["binding_limit"] == "consumption_target"
    assert option["annual_production_kwh"] == 5830  # 3.96 x 1472.13 = 5829.63
    assert option["panel"]["model"] == "Vertex S+ TSM-NEG9RH.25 (440 W)"
    assert quote["assumptions"]["coverage_ratio"] == 0.8
    assert quote["assumptions"]["pvgis_inputs"] == {
        "source": "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc",
        "latitude": 39.933,
        "longitude": 32.86,
        "tilt_deg": 30,
        "aspect_deg": 0,
        "system_loss_percent": 14,
    }
    [pvgis_request] = requests_seen
    assert pvgis_request.url.params["loss"] == "14"


def test_flat_roof_sends_the_configured_tilt_and_south_facing_aspect_to_pvgis(
    wired_client: TestClient, requests_seen: list[httpx.Request]
) -> None:
    body = valid_body()
    body["roof"].update(roof_type="flat", azimuth_deg=90, tilt_deg=40)

    response = wired_client.post("/quotes", json=body)

    assert response.status_code == 201
    [pvgis_request] = requests_seen
    assert pvgis_request.url.params["angle"] == "15"
    assert pvgis_request.url.params["aspect"] == "0"
    pvgis_inputs = response.json()["assumptions"]["pvgis_inputs"]
    assert pvgis_inputs["tilt_deg"] == 15
    assert pvgis_inputs["aspect_deg"] == 0


def test_system_clock_reports_a_date() -> None:
    today = SystemClock().today()

    assert abs(today - datetime.now(UTC).date()) <= timedelta(days=1)
