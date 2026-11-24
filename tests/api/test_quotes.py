"""POST /quotes through the real FastAPI app with a fake Specific Yield provider.

Fixed inputs (see tests/factories.py): panel 0.5 kWp / 2.0 m2, coverage ratio 0.80,
specific yield 1,500 kWh/kWp unless a test says otherwise.
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sunquote.domain.errors import UpstreamUnavailableError
from tests.factories import MONTHLY_YIELD_KWH_PER_KWP, make_specific_yield
from tests.fakes import FakeSpecificYieldProvider

PROBLEM_JSON = "application/problem+json"


def valid_body() -> dict[str, Any]:
    return {
        "customer": {
            "name": "Şule Öztürk",
            "phone": "+90 555 000 00 00",
            "email": "sule@example.com",
        },
        "site": {"latitude": 39.9334, "longitude": 32.8597},
        "roof": {
            "roof_type": "pitched",
            "usable_area_m2": 40,
            "azimuth_deg": 180,
            "tilt_deg": 30,
        },
        "consumption": {"monthly_consumption_kwh": 500},
        "subscriber_group": "residential",
    }


def with_change(path: str, value: Any) -> dict[str, Any]:
    """The valid body with one nested field replaced; a `value` of `...` deletes the field."""
    body = valid_body()
    *parents, leaf = path.split(".")
    target = body
    for key in parents:
        target = target[key]
    if value is ...:
        del target[leaf]
    else:
        target[leaf] = value
    return body


def test_creates_a_quote_with_one_consumption_matched_option(client: TestClient) -> None:
    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    assert quote["customer"] == {
        "name": "Şule Öztürk",
        "phone": "+90 555 000 00 00",
        "email": "sule@example.com",
    }
    assert quote["quote_date"] == "2026-11-24"
    [option] = quote["system_options"]
    assert option["strategy"] == "consumption_matched"
    assert option["panel_count"] == 8
    assert option["capacity_kwp"] == 4.0
    assert option["binding_limit"] == "consumption_target"
    assert option["panel"] == {
        "panel_id": "test-panel-500w",
        "manufacturer": "Test",
        "model": "T-500",
        "power_w": 500,
    }
    assert option["annual_production_kwh"] == 6000
    assert [m["month"] for m in option["monthly_production_kwh"]] == list(range(1, 13))
    assert [m["production_kwh"] for m in option["monthly_production_kwh"]] == [
        280, 360, 480, 560, 640, 700, 740, 680, 560, 440, 320, 240,
    ]  # fmt: skip


def test_displayed_figures_are_rounded_by_the_policy(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    monthly = (Decimal("69.17"), *MONTHLY_YIELD_KWH_PER_KWP[1:])
    specific_yield_provider.specific_yield = make_specific_yield(annual="1472.13", monthly=monthly)

    option = client.post("/quotes", json=valid_body()).json()["system_options"][0]

    # 6000 kWh / 1472.13 kWh/kWp = 4.07 kWp -> 8 panels = 4 kWp. 4 x 1472.13 = 5888.52 kWh.
    assert option["capacity_kwp"] == 4.0
    assert option["annual_production_kwh"] == 5889
    # 4 x 69.17 = 276.68 kWh
    assert option["monthly_production_kwh"][0]["production_kwh"] == 277


def test_assumptions_record_the_submitted_input_pvgis_inputs_ratio_and_panel(
    client: TestClient,
) -> None:
    quote = client.post("/quotes", json=valid_body()).json()

    assumptions = quote["assumptions"]
    assert assumptions["submitted_request"] == valid_body()
    assert assumptions["pvgis_inputs"] == {
        "source": "test",
        "latitude": 39.93,
        "longitude": 32.86,
        "tilt_deg": 30,
        "aspect_deg": 0,
        "system_loss_percent": 14,
    }
    assert assumptions["coverage_ratio"] == 0.8
    assert assumptions["default_panel"] == {
        "panel_id": "test-panel-500w",
        "manufacturer": "Test",
        "model": "T-500",
        "power_w": 500,
        "length_mm": 2000,
        "width_mm": 1000,
        "area_m2": 2.0,
        "degradation_rate_per_year": 0.005,
    }


def test_the_same_request_gives_the_same_quote(client: TestClient) -> None:
    first = client.post("/quotes", json=valid_body()).json()
    second = client.post("/quotes", json=valid_body()).json()

    assert first == second


def test_optional_customer_details_may_be_omitted(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("customer", {"name": "Mehmet Kaya"}))

    assert response.status_code == 201
    assert response.json()["customer"] == {"name": "Mehmet Kaya", "phone": None, "email": None}


def test_pvgis_is_asked_for_the_roof_orientation_at_the_site(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    body = with_change("roof.azimuth_deg", 225)
    body["roof"]["tilt_deg"] = 35

    client.post("/quotes", json=body)

    [query] = specific_yield_provider.queries
    assert (query.azimuth_deg, query.tilt_deg) == (Decimal("225"), Decimal("35"))
    assert query.coordinates.latitude == Decimal("39.9334")
    assert query.coordinates.longitude == Decimal("32.8597")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("customer.name", ""),
        ("customer.name", "   "),
        ("customer.name", ...),
        ("customer.email", "not-an-email"),
        ("site.latitude", 90.5),
        ("site.latitude", -91),
        ("site.longitude", 180.5),
        ("site.longitude", -181),
        ("site.latitude", ...),
        ("roof.usable_area_m2", 0),
        ("roof.usable_area_m2", -5),
        ("roof.azimuth_deg", 360),
        ("roof.azimuth_deg", -1),
        ("roof.tilt_deg", 90.5),
        ("roof.tilt_deg", -1),
        ("roof.roof_type", "gabled"),
        ("roof.roof_type", "flat"),
        ("consumption.monthly_consumption_kwh", 0),
        ("consumption.monthly_consumption_kwh", -3),
        ("consumption.monthly_consumption_kwh", ...),
        ("subscriber_group", ...),
    ],
)
def test_invalid_input_is_a_422_problem_naming_the_field(
    client: TestClient, path: str, value: Any
) -> None:
    response = client.post("/quotes", json=with_change(path, value))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:validation-error"
    assert problem["status"] == 422
    assert path in [error["field"] for error in problem["errors"]]


def test_boundary_values_are_accepted(client: TestClient) -> None:
    body = valid_body()
    body["roof"].update(azimuth_deg=0, tilt_deg=0)
    body["site"].update(latitude=-90, longitude=180)

    assert client.post("/quotes", json=body).status_code == 201


def test_flat_roofs_are_rejected_until_the_flat_roof_ticket(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("roof.roof_type", "flat"))

    assert response.status_code == 422
    messages = " ".join(error["message"] for error in response.json()["errors"])
    assert "flat" in messages


def test_malformed_json_is_a_validation_problem(client: TestClient) -> None:
    response = client.post(
        "/quotes", content="{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["type"] == "urn:sunquote:problem:validation-error"


@pytest.mark.parametrize("group", ["commercial", "Residential", ""])
def test_other_subscriber_groups_are_unsupported(client: TestClient, group: str) -> None:
    response = client.post("/quotes", json=with_change("subscriber_group", group))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:unsupported-subscriber-group"
    assert problem["title"] == "Unsupported Subscriber Group"
    assert "residential" in problem["detail"]


def test_a_roof_that_fits_no_panel_is_a_no_viable_system_problem(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("roof.usable_area_m2", 2))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:no-viable-system"
    assert problem["status"] == 422


def test_pvgis_outage_is_a_503_problem(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    specific_yield_provider.error = UpstreamUnavailableError("PVGIS", "the request timed out")

    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:upstream-unavailable"
    assert problem["status"] == 503
    assert "PVGIS" in problem["detail"]


def test_openapi_documents_the_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "201" in paths["/quotes"]["post"]["responses"]
