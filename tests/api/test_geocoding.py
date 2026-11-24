from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sunquote.domain.errors import (
    AddressNotFoundError,
    DomainError,
    UpstreamUnavailableError,
)
from tests.api.test_quotes import PROBLEM_JSON, valid_body
from tests.fakes import FakeGeocoder, FakeSpecificYieldProvider

ADDRESS = "  An\u0131tkabir, Ankara  "


@pytest.mark.parametrize(
    ("site", "field"),
    [
        ({}, "site.address"),
        ({"address": "   "}, "site.address"),
        ({"latitude": 39.93, "address": "Ankara"}, "site.longitude"),
        ({"longitude": 32.86}, "site.latitude"),
    ],
)
def test_site_requires_an_address_or_a_complete_coordinate_pair(
    client: TestClient, site: dict[str, Any], field: str
) -> None:
    response = client.post("/quotes", json={**valid_body(), "site": site})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert [error["field"] for error in response.json()["errors"]] == [field]


def test_an_address_is_resolved_recorded_and_listed(
    client: TestClient, geocoder: FakeGeocoder, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    site = {"address": ADDRESS}
    response = client.post("/quotes", json={**valid_body(), "site": site})

    assert response.status_code == 201
    quote = response.json()
    assumptions = quote["assumptions"]
    assert assumptions["submitted_request"]["site"] == {
        "address": ADDRESS,
        "latitude": None,
        "longitude": None,
    }
    assert assumptions["geocoding_result"] == {
        "display_name": "An\u0131tkabir, Çankaya, Ankara, Türkiye",
        "latitude": 39.9267385,
        "longitude": 32.8365635,
    }
    assert geocoder.addresses == [ADDRESS]
    [query] = specific_yield_provider.queries
    assert query.coordinates.latitude == Decimal("39.9267385")
    assert query.coordinates.longitude == Decimal("32.8365635")
    assert client.get(f"/quotes/{quote['id']}").json() == quote
    [item] = client.get("/quotes").json()["items"]
    assert (item["district"], item["province"]) == ("Çankaya", "Ankara")


def test_coordinates_take_precedence_and_keep_the_entered_address(
    client: TestClient, geocoder: FakeGeocoder, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    body = valid_body()
    body["site"]["address"] = ADDRESS

    response = client.post("/quotes", json=body)

    assert response.status_code == 201
    assumptions = response.json()["assumptions"]
    assert assumptions["submitted_request"]["site"] == body["site"]
    assert assumptions["geocoding_result"] is None
    assert geocoder.addresses == []
    [query] = specific_yield_provider.queries
    assert query.coordinates.latitude == Decimal("39.9334")
    assert query.coordinates.longitude == Decimal("32.8597")
    [item] = client.get("/quotes").json()["items"]
    assert item["district"] is None
    assert item["province"] is None


@pytest.mark.parametrize(
    ("error", "status", "slug"),
    [
        (AddressNotFoundError(), 422, "address-not-found"),
        (
            UpstreamUnavailableError("Nominatim", "the request timed out"),
            503,
            "upstream-unavailable",
        ),
    ],
)
def test_geocoding_failures_return_a_problem_and_store_no_quote(
    client: TestClient, geocoder: FakeGeocoder, error: DomainError, status: int, slug: str
) -> None:
    geocoder.error = error

    response = client.post("/quotes", json={**valid_body(), "site": {"address": ADDRESS}})

    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["type"] == f"urn:sunquote:problem:{slug}"
    assert client.get("/quotes").json()["total"] == 0
