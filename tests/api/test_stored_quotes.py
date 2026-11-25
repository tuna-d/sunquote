"""Storing, fetching and listing Quotes through the API, with an in-memory repository.

Fixed inputs as in tests/api/test_quotes.py: the default request is a 4.0 kWp system that
costs 132,500 TRY before VAT and 159,000 TRY with it. The fake repository creates each Quote
one minute after the previous one.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from sunquote.domain.errors import UpstreamUnavailableError
from tests.api.test_quotes import PROBLEM_JSON, valid_body, with_change
from tests.fakes import (
    FakeExchangeRateProvider,
    FakeQuoteRepository,
    FakeSpecificYieldProvider,
)


def create(client: TestClient, name: str = "Şule Öztürk") -> dict[str, object]:
    body = with_change("customer.name", name)
    response = client.post("/quotes", json=body)
    assert response.status_code == 201
    created: dict[str, object] = response.json()
    return created


def test_a_created_quote_has_an_id_a_number_a_creation_time_and_a_valid_until_date(
    client: TestClient,
) -> None:
    quote = create(client)

    assert isinstance(quote["id"], str)
    assert quote["quote_number"] == "SQ-2026-000001"
    assert quote["is_sample"] is False
    assert quote["quote_date"] == "2026-11-24"
    assert quote["valid_until"] == "2026-12-09"  # 15 days of validity
    assert str(quote["created_at"]).startswith("2026-11-24T")
    assumptions = quote["assumptions"]
    assert isinstance(assumptions, dict)
    assert assumptions["pricing"]["validity_period_days"] == 15


def test_quote_numbers_count_up(client: TestClient) -> None:
    numbers = [create(client)["quote_number"] for _ in range(3)]

    assert numbers == ["SQ-2026-000001", "SQ-2026-000002", "SQ-2026-000003"]


def test_a_stored_quote_is_fetched_by_id_exactly_as_it_was_created(client: TestClient) -> None:
    created = create(client)

    response = client.get(f"/quotes/{created['id']}")

    assert response.status_code == 200
    assert response.json()["is_sample"] is False
    assert response.json() == created


def test_an_unknown_id_is_a_404_problem(client: TestClient) -> None:
    response = client.get(f"/quotes/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:quote-not-found"
    assert problem["status"] == 404


def test_a_malformed_id_is_a_validation_problem(client: TestClient) -> None:
    response = client.get("/quotes/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "quote_id"


def test_the_list_is_newest_first_and_each_item_summarises_the_quote(client: TestClient) -> None:
    created = [create(client, name) for name in ("Ayşe", "Berk", "Ceren")]

    page = client.get("/quotes").json()

    assert page["total"] == 3
    assert [item["customer_name"] for item in page["items"]] == ["Ceren", "Berk", "Ayşe"]
    newest = page["items"][0]
    assert newest == {
        "id": created[2]["id"],
        "quote_number": "SQ-2026-000003",
        "created_at": created[2]["created_at"],
        "is_sample": False,
        "customer_name": "Ceren",
        "district": None,
        "province": None,
        "system_option_count": 2,  # Consumption-Matched and Roof-Max
        "capacity_kwp": 4.0,
        "total_try": 159000,
    }


def test_the_list_is_paginated(client: TestClient) -> None:
    for index in range(5):
        create(client, f"Customer {index + 1}")

    first = client.get("/quotes", params={"page": 1, "page_size": 2}).json()
    last = client.get("/quotes", params={"page": 3, "page_size": 2}).json()
    beyond = client.get("/quotes", params={"page": 4, "page_size": 2}).json()

    assert (first["page"], first["page_size"], first["total"]) == (1, 2, 5)
    assert [item["customer_name"] for item in first["items"]] == ["Customer 5", "Customer 4"]
    assert [item["customer_name"] for item in last["items"]] == ["Customer 1"]
    assert beyond["items"] == []


def test_an_empty_list_is_a_page_with_no_items(client: TestClient) -> None:
    page = client.get("/quotes").json()

    assert page == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_page_parameters_are_validated(client: TestClient) -> None:
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        response = client.get("/quotes", params=params)

        assert response.status_code == 422, params
        assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_nothing_is_stored_when_validation_fails(
    client: TestClient, quote_repository: FakeQuoteRepository
) -> None:
    response = client.post("/quotes", json=with_change("roof.usable_area_m2", -1))

    assert response.status_code == 422
    assert quote_repository.stored == []
    assert quote_repository.issued_numbers == []


def test_nothing_is_stored_when_no_viable_system_exists(
    client: TestClient, quote_repository: FakeQuoteRepository
) -> None:
    response = client.post("/quotes", json=with_change("roof.usable_area_m2", 2))

    assert response.status_code == 422
    assert quote_repository.stored == []


def test_nothing_is_stored_when_an_upstream_is_down(
    client: TestClient,
    quote_repository: FakeQuoteRepository,
    specific_yield_provider: FakeSpecificYieldProvider,
    exchange_rate_provider: FakeExchangeRateProvider,
) -> None:
    specific_yield_provider.error = UpstreamUnavailableError("PVGIS", "timed out")
    assert client.post("/quotes", json=valid_body()).status_code == 503
    specific_yield_provider.error = None
    exchange_rate_provider.error = UpstreamUnavailableError("TCMB", "timed out")
    assert client.post("/quotes", json=valid_body()).status_code == 503

    assert quote_repository.stored == []
    assert client.get("/quotes").json()["total"] == 0


def test_the_api_has_no_way_to_change_a_stored_quote(client: TestClient) -> None:
    created = create(client)
    url = f"/quotes/{created['id']}"

    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(url).status_code == 405

    assert client.get(url).json() == created


def test_openapi_documents_the_read_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "404" in paths["/quotes/{quote_id}"]["get"]["responses"]
    assert "200" in paths["/quotes"]["get"]["responses"]
