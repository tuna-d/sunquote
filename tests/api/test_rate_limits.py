"""Per-IP rate limits on the two write endpoints (ADR 0007), through the real app."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from sunquote.config import Settings
from sunquote.domain.rate_limit import FixedWindowRateLimiter
from tests.api.test_quotes import valid_body
from tests.conftest import ClientFactory
from tests.fakes import FakeQuoteRepository, FixedClock, InMemoryCounterStore

PROBLEM_JSON = "application/problem+json"
HOUR_START = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
ASSISTANT_BODY = {"messages": [{"role": "user", "content": "Merhaba"}]}
VERCEL_IP_HEADER = "x-vercel-forwarded-for"


class Harness:
    """A client on a fake clock, so tests can move through the hour."""

    def __init__(self, client_factory: ClientFactory, settings: Settings) -> None:
        self.clock = FixedClock(now=HOUR_START + timedelta(minutes=15))
        store = InMemoryCounterStore(clock=self.clock.now)
        self.client = client_factory(
            settings=settings, rate_limiter=FixedWindowRateLimiter(store, self.clock)
        )

    def client_from(self, ip: str) -> TestClient:
        """Another client of the same app, connecting from `ip`."""
        return TestClient(self.client.app, client=(ip, 50000))

    def advance(self, **delta: float) -> None:
        self.clock._now += timedelta(**delta)


@pytest.fixture
def harness(client_factory: ClientFactory) -> Harness:
    return Harness(
        client_factory,
        Settings(rate_limit_quotes_per_hour=2, rate_limit_assistant_messages_per_hour=3),
    )


def test_the_defaults_are_ten_quotes_and_twenty_assistant_messages_an_hour() -> None:
    settings = Settings()

    assert settings.rate_limit_quotes_per_hour == 10
    assert settings.rate_limit_assistant_messages_per_hour == 20
    assert settings.behind_vercel is False


def test_a_quote_over_the_limit_is_refused_with_problem_json_and_retry_after(
    harness: Harness,
) -> None:
    assert harness.client.post("/quotes", json=valid_body()).status_code == 201
    assert harness.client.post("/quotes", json=valid_body()).status_code == 201

    response = harness.client.post("/quotes", json=valid_body())

    assert response.status_code == 429
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["retry-after"] == str(45 * 60)
    body = response.json()
    assert body["type"] == "urn:sunquote:problem:rate-limited"
    assert body["status"] == 429
    assert "quote" in body["detail"].lower()


def test_a_refused_quote_is_not_created(
    harness: Harness, quote_repository: FakeQuoteRepository
) -> None:
    for _ in range(3):
        harness.client.post("/quotes", json=valid_body())

    assert len(quote_repository.stored) == 2


def test_assistant_messages_over_the_limit_are_refused(harness: Harness) -> None:
    statuses = [
        harness.client.post("/assistant/messages", json=ASSISTANT_BODY).status_code
        for _ in range(4)
    ]

    # Under the limit the unconfigured Assistant answers 503; the fourth call never gets there.
    assert statuses == [503, 503, 503, 429]
    refused = harness.client.post("/assistant/messages", json=ASSISTANT_BODY)
    assert refused.headers["retry-after"] == str(45 * 60)
    assert refused.json()["type"] == "urn:sunquote:problem:rate-limited"


def test_each_endpoint_has_its_own_counter(harness: Harness) -> None:
    for _ in range(3):
        harness.client.post("/quotes", json=valid_body())

    assert harness.client.post("/assistant/messages", json=ASSISTANT_BODY).status_code == 503


def test_each_client_ip_has_its_own_counter(harness: Harness) -> None:
    for _ in range(3):
        harness.client_from("203.0.113.7").post("/quotes", json=valid_body())

    assert harness.client_from("203.0.113.7").post("/quotes", json=valid_body()).status_code == 429
    assert harness.client_from("198.51.100.9").post("/quotes", json=valid_body()).status_code == 201


def test_the_limit_resets_when_the_next_hour_starts(harness: Harness) -> None:
    for _ in range(3):
        harness.client.post("/quotes", json=valid_body())

    harness.advance(minutes=45)

    assert harness.client.post("/quotes", json=valid_body()).status_code == 201


def test_read_endpoints_and_health_are_not_limited(harness: Harness) -> None:
    for _ in range(15):
        assert harness.client.get("/health").status_code == 200
        assert harness.client.get("/quotes").status_code == 200


def test_a_call_over_the_limit_is_refused_before_its_body_is_checked(harness: Harness) -> None:
    for _ in range(2):
        harness.client.post("/quotes", json=valid_body())

    response = harness.client.post("/quotes", json={})

    assert response.status_code == 429


def test_the_vercel_header_is_ignored_unless_the_app_runs_behind_vercel(
    harness: Harness,
) -> None:
    for number in range(3):
        harness.client.post(
            "/quotes", json=valid_body(), headers={VERCEL_IP_HEADER: f"10.0.0.{number}"}
        )

    # A caller cannot dodge the limit by sending its own header.
    response = harness.client.post(
        "/quotes", json=valid_body(), headers={VERCEL_IP_HEADER: "10.9.9.9"}
    )

    assert response.status_code == 429


def test_behind_vercel_the_client_is_the_ip_vercel_forwards(client_factory: ClientFactory) -> None:
    harness = Harness(
        client_factory,
        Settings(rate_limit_quotes_per_hour=1, behind_vercel=True),
    )
    first = {VERCEL_IP_HEADER: "203.0.113.7"}
    other = {VERCEL_IP_HEADER: "198.51.100.9"}

    assert harness.client.post("/quotes", json=valid_body(), headers=first).status_code == 201
    assert harness.client.post("/quotes", json=valid_body(), headers=first).status_code == 429
    assert harness.client.post("/quotes", json=valid_body(), headers=other).status_code == 201


def test_behind_vercel_a_list_of_addresses_counts_as_its_first_one(
    client_factory: ClientFactory,
) -> None:
    harness = Harness(client_factory, Settings(rate_limit_quotes_per_hour=1, behind_vercel=True))

    harness.client.post(
        "/quotes", json=valid_body(), headers={VERCEL_IP_HEADER: "203.0.113.7, 10.1.1.1"}
    )
    response = harness.client.post(
        "/quotes", json=valid_body(), headers={VERCEL_IP_HEADER: "203.0.113.7"}
    )

    assert response.status_code == 429


def test_behind_vercel_a_missing_header_falls_back_to_the_connection(
    client_factory: ClientFactory,
) -> None:
    harness = Harness(client_factory, Settings(rate_limit_quotes_per_hour=1, behind_vercel=True))

    assert harness.client.post("/quotes", json=valid_body()).status_code == 201
    assert harness.client.post("/quotes", json=valid_body()).status_code == 429


def test_without_a_limiter_nothing_is_limited(client: TestClient) -> None:
    for _ in range(12):
        assert client.post("/quotes", json=valid_body()).status_code == 201


def test_a_failing_counter_store_does_not_take_the_endpoint_down(
    client_factory: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenStore:
        async def increment(self, key: str, *, ttl_seconds: int) -> int:
            raise OSError("counter store is down")

    client = client_factory(rate_limiter=FixedWindowRateLimiter(BrokenStore(), FixedClock()))

    with caplog.at_level("WARNING", logger="sunquote"):
        response = client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    assert "rate limit" in caplog.text.lower()
