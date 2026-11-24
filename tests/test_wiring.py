"""The real adapters and shipped data files wired together, with recorded PVGIS and TCMB
responses."""

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

RECORDINGS = Path(__file__).parent / "adapters" / "recordings"
RECORDING = RECORDINGS / "pvgis_pvcalc_ankara.json"
TCMB_MONDAY = RECORDINGS / "tcmb_2026-11-23_monday.xml"


@pytest.fixture
def requests_seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def wired_client(requests_seen: list[httpx.Request]) -> Iterator[TestClient]:
    def upstream(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.host == "www.tcmb.gov.tr":
            # Whatever the quote date, serve the Monday 2026-11-23 file (USD selling 50.6026).
            return httpx.Response(200, content=TCMB_MONDAY.read_bytes())
        return httpx.Response(200, text=RECORDING.read_text(encoding="utf-8"))

    settings = Settings()
    dependencies = build_dependencies(settings, transport=httpx.MockTransport(upstream))
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
    pvgis_request = next(r for r in requests_seen if r.url.host != "www.tcmb.gov.tr")
    assert pvgis_request.url.params["loss"] == "14"


def test_quote_is_priced_from_the_shipped_prices_and_the_tcmb_rate(
    wired_client: TestClient, requests_seen: list[httpx.Request]
) -> None:
    quote = wired_client.post("/quotes", json=valid_body()).json()

    # 9 Trina panels (3.96 kWp). The 3 kW Huawei is the cheapest in range (3.96 / 3 = 1.32).
    [option] = quote["system_options"]
    assert option["inverter"]["model"] == "SUN2000-3KTL-M1"
    # USD: 9 x 76 + 650 + 120 x 3.96 = 684 + 650 + 475.2 = 1,809.2 -> x 50.6026 = 91,550.25
    # + labour 4,000 x 3.96 = 15,840 + fixed 20,000 = 127,390.25 (Installation Cost)
    # x 1.25 = 159,237.81 (Sale Price); VAT 20% = 31,847.56; total 191,085.37
    assert option["price"] == {
        "installation_cost_try": 127390,
        "sale_price_try": 159238,
        "vat_try": 31848,
        "total_try": 191085,
    }
    rate = quote["assumptions"]["exchange_rate"]
    assert (rate["rate"], rate["overridden"]) == (50.6026, False)
    tcmb_requests = [r for r in requests_seen if r.url.host == "www.tcmb.gov.tr"]
    assert tcmb_requests
    assert tcmb_requests[0].url.path.endswith(".xml")


def test_system_clock_reports_a_date() -> None:
    today = SystemClock().today()

    assert abs(today - datetime.now(UTC).date()) <= timedelta(days=1)
