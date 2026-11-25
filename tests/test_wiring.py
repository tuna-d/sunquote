"""The real adapters and shipped data files wired together, with recorded PVGIS and TCMB
responses."""

import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.asyncio.connection import Connection, SSLConnection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from sunquote.adapters.clock import SystemClock
from sunquote.adapters.gemini import GeminiNarrativeWriter
from sunquote.adapters.gemini_conversation import GeminiConversationModel
from sunquote.adapters.postgres.counter_store import PostgresCounterStore
from sunquote.adapters.postgres.quote_repository import PostgresQuoteRepository
from sunquote.adapters.redis_cache import CachedGeocoder
from sunquote.adapters.redis_counter_store import RedisCounterStore
from sunquote.api.app import create_app
from sunquote.bootstrap import build_dependencies
from sunquote.config import Settings
from tests.api.test_quotes import valid_body
from tests.fakes import (
    FakeQuoteRepository,
    InMemoryCounterStore,
    ScriptedConversationModel,
    ScriptedNarrativeWriter,
)

RECORDINGS = Path(__file__).parent / "adapters" / "recordings"
RECORDING = RECORDINGS / "pvgis_pvcalc_ankara.json"
TCMB_MONDAY = RECORDINGS / "tcmb_2026-11-23_monday.xml"


@pytest.fixture
def requests_seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def recorded_transport(requests_seen: list[httpx.Request]) -> httpx.MockTransport:
    def upstream(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.host == "nominatim.openstreetmap.org":
            return httpx.Response(200, content=(RECORDINGS / "nominatim_ankara.json").read_bytes())
        if request.url.host == "www.tcmb.gov.tr":
            # Whatever the quote date, serve the Monday 2026-11-23 file (USD selling 50.6026).
            return httpx.Response(200, content=TCMB_MONDAY.read_bytes())
        return httpx.Response(200, text=RECORDING.read_text(encoding="utf-8"))

    return httpx.MockTransport(upstream)


@pytest.fixture
def wired_client(recorded_transport: httpx.MockTransport) -> Iterator[TestClient]:
    # No key, even when a developer's `.env` sets one for the evals.
    settings = Settings(redis_url=None, gemini_api_key=None)
    dependencies = build_dependencies(
        settings,
        transport=recorded_transport,
        quote_repository=FakeQuoteRepository(),
    )
    with TestClient(create_app(settings, dependencies)) as client:
        yield client


@pytest.mark.parametrize("override", [False, True], ids=["tcmb", "override"])
def test_an_unreachable_redis_cache_still_allows_quote_creation(
    recorded_transport: httpx.MockTransport,
    requests_seen: list[httpx.Request],
    caplog: pytest.LogCaptureFixture,
    override: bool,
) -> None:
    repository = FakeQuoteRepository()
    body = {**valid_body(), "site": {"address": "An\u0131tkabir, Ankara"}}
    if override:
        body["exchange_rate_override"] = {"rate": 45, "date": "2026-11-01"}
    # Reserve a port without listening so the Redis connection is refused.
    with socket.socket() as unreachable:
        unreachable.bind(("127.0.0.1", 0))
        port = unreachable.getsockname()[1]
        settings = Settings(redis_url=f"redis://127.0.0.1:{port}/0")
        dependencies = build_dependencies(
            settings, transport=recorded_transport, quote_repository=repository
        )
        with TestClient(create_app(settings, dependencies)) as client:
            response = client.post("/quotes", json=body)

    assert response.status_code == 201
    assert len(repository.stored) == 1
    rate = response.json()["assumptions"]["exchange_rate"]
    assert rate["overridden"] is override
    assert any(request.url.host == "www.tcmb.gov.tr" for request in requests_seen) is not override
    assert sum("Redis cache read failed" in message for message in caplog.messages) == (
        2 if override else 3
    )


def test_quote_from_shipped_data_files_and_recorded_pvgis_response(
    wired_client: TestClient, requests_seen: list[httpx.Request]
) -> None:
    response = wired_client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    option = quote["system_options"][0]  # Consumption-Matched
    # 6000 kWh / 1472.13 kWh/kWp = 4.076 kWp; 4.076 / 0.44 kWp = 9.26 -> 9 panels = 3.96 kWp.
    assert option["panel_count"] == 9
    assert option["capacity_kwp"] == 3.96
    assert option["binding_limit"] == "consumption_target"
    assert option["annual_production_kwh"] == 5830  # 3.96 x 1472.13 = 5829.63
    assert option["panel"]["model"] == "Vertex S+ TSM-NEG9RH.25 (440 W)"
    assert quote["assumptions"]["coverage_ratio"] == "0.80"
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
    option = quote["system_options"][0]  # Consumption-Matched
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
    assert (rate["rate"], rate["overridden"]) == ("50.6026", False)
    tcmb_requests = [r for r in requests_seen if r.url.host == "www.tcmb.gov.tr"]
    assert tcmb_requests
    assert tcmb_requests[0].url.path.endswith(".xml")


def test_flat_roof_sends_the_configured_tilt_and_south_facing_aspect_to_pvgis(
    wired_client: TestClient, requests_seen: list[httpx.Request]
) -> None:
    body = valid_body()
    body["roof"].update(roof_type="flat", azimuth_deg=90, tilt_deg=40)

    response = wired_client.post("/quotes", json=body)

    assert response.status_code == 201
    pvgis_request = next(r for r in requests_seen if r.url.host != "www.tcmb.gov.tr")
    assert pvgis_request.url.params["angle"] == "15"
    assert pvgis_request.url.params["aspect"] == "0"
    pvgis_inputs = response.json()["assumptions"]["pvgis_inputs"]
    assert pvgis_inputs["tilt_deg"] == 15
    assert pvgis_inputs["aspect_deg"] == 0


def test_system_clock_reports_a_date() -> None:
    today = SystemClock().today()

    assert abs(today - datetime.now(UTC).date()) <= timedelta(days=1)


def test_address_quotes_use_the_wired_geocoder_and_send_its_coordinates_to_pvgis(
    wired_client: TestClient,
) -> None:
    body = {**valid_body(), "site": {"address": "An\u0131tkabir, Ankara"}}

    response = wired_client.post("/quotes", json=body)

    assert response.status_code == 201
    assumptions = response.json()["assumptions"]
    assert assumptions["geocoding_result"]["latitude"] == 39.9267385
    assert assumptions["geocoding_result"]["longitude"] == 32.8365635
    pvgis = assumptions["pvgis_inputs"]
    assert (pvgis["latitude"], pvgis["longitude"]) == (39.927, 32.837)


def test_the_real_wiring_migrates_the_database_on_startup_without_connecting() -> None:
    # Building the dependencies opens no connection: the engine connects lazily.
    dependencies = build_dependencies(Settings())

    assert len(dependencies.startup) == 1
    assert build_dependencies(Settings(migrate_on_startup=False)).startup == ()


def test_an_injected_repository_means_no_migration_and_no_database() -> None:
    dependencies = build_dependencies(Settings(), quote_repository=FakeQuoteRepository())

    assert dependencies.startup == ()


def test_savings_come_from_the_shipped_tariff_and_financial_assumptions(
    wired_client: TestClient,
) -> None:
    quote = wired_client.post("/quotes", json=valid_body()).json()

    option = quote["system_options"][0]  # Consumption-Matched
    savings = option["savings"]
    assert len(savings["cash_flow"]) == 25
    # 3.96 kWp x 1,472.13 = 5,829.63 kWh; 85% self-consumed = 4,955.19 kWh of the 6,000 kWh a
    # year. The grid bill (2,920 kWh at 3.24 + 3,080 kWh at 4.86 = 24,429.60) drops to
    # 1,044.81 kWh x 3.24 = 3,385.19: 21,044.41 saved. The other 874.45 kWh export at 2.92.
    first_year = savings["cash_flow"][0]
    assert first_year["self_consumed_kwh"] == 4955
    assert first_year["exported_kwh"] == 874
    assert first_year["self_consumption_savings_try"] == 21044
    assert first_year["export_income_try"] == 2553
    assert savings["first_year_annual_savings_try"] == 23598  # 23,597.79
    assumptions = quote["assumptions"]
    assert assumptions["tariff"]["tier_threshold_kwh_per_year"] == "2920"
    assert assumptions["tariff"]["valid_from"] == "2026-04-04"
    assert assumptions["low_tier_consumption_kwh"] == 2920
    assert assumptions["high_tier_consumption_kwh"] == 3080
    assert assumptions["financial"]["lifetime_years"] == 25


def test_the_wired_app_has_no_narrative_writer_yet_so_quotes_record_a_fallback(
    wired_client: TestClient,
) -> None:
    quote = wired_client.post("/quotes", json=valid_body()).json()

    narrative = quote["narrative"]
    assert (narrative["source"], narrative["model"]) == ("fallback", None)
    assert narrative["greeting"] == "Sayın Şule Öztürk,"
    assert datetime.fromisoformat(narrative["generated_at"]).utcoffset() == timedelta(0)


def test_without_a_gemini_key_no_narrative_writer_is_wired() -> None:
    dependencies = build_dependencies(
        Settings(gemini_api_key=None), quote_repository=FakeQuoteRepository()
    )

    assert dependencies.quote_service._narrative_writer is None


def test_with_a_gemini_key_the_gemini_writer_is_wired_with_the_configured_model() -> None:
    settings = Settings(gemini_api_key=SecretStr("key-123"), gemini_model="gemini-test-model")

    dependencies = build_dependencies(settings, quote_repository=FakeQuoteRepository())

    writer = dependencies.quote_service._narrative_writer
    assert isinstance(writer, GeminiNarrativeWriter)
    assert writer.model_name == "gemini-test-model"


def test_an_injected_narrative_writer_wins_over_the_gemini_key() -> None:
    injected = ScriptedNarrativeWriter()
    settings = Settings(gemini_api_key=SecretStr("key-123"))

    dependencies = build_dependencies(
        settings, quote_repository=FakeQuoteRepository(), narrative_writer=injected
    )

    assert dependencies.quote_service._narrative_writer is injected


def test_a_quote_gets_a_gemini_narrative_through_the_wired_app(
    recorded_transport: httpx.MockTransport,
    requests_seen: list[httpx.Request],
) -> None:
    gemini_text = (RECORDINGS / "gemini_generate_content_success.json").read_bytes()

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "generativelanguage.googleapis.com":
            requests_seen.append(request)
            return httpx.Response(200, content=gemini_text)
        return recorded_transport.handler(request)  # type: ignore[attr-defined,no-any-return]

    settings = Settings(redis_url=None, gemini_api_key=SecretStr("key-123"))
    dependencies = build_dependencies(
        settings, transport=httpx.MockTransport(upstream), quote_repository=FakeQuoteRepository()
    )
    with TestClient(create_app(settings, dependencies)) as client:
        quote = client.post("/quotes", json=valid_body()).json()

    assert quote["narrative"]["source"] == "llm"
    assert quote["narrative"]["model"] == "gemini-3.5-flash-lite"
    assert quote["narrative"]["greeting"] == "Merhaba Şule Öztürk, teklifiniz hazır."
    gemini_request = next(
        r for r in requests_seen if r.url.host == "generativelanguage.googleapis.com"
    )
    assert gemini_request.headers["x-goog-api-key"] == "key-123"


def test_without_a_gemini_key_no_conversation_model_is_wired_and_the_assistant_is_off(
    wired_client: TestClient,
) -> None:
    response = wired_client.post(
        "/assistant/messages", json={"messages": [{"role": "user", "content": "Merhaba"}]}
    )

    assert response.status_code == 503
    assert response.json()["type"] == "urn:sunquote:problem:assistant-not-configured"
    assert wired_client.post("/quotes", json=valid_body()).status_code == 201


def test_with_a_gemini_key_the_conversation_model_is_wired_with_model_and_time_budget() -> None:
    settings = Settings(
        gemini_api_key=SecretStr("key-123"),
        gemini_model="gemini-test-model",
        assistant_timeout_seconds=12.5,
    )

    dependencies = build_dependencies(settings, quote_repository=FakeQuoteRepository())

    assert isinstance(dependencies.conversation_model, GeminiConversationModel)
    assert dependencies.conversation_model.model_name == "gemini-test-model"
    assert dependencies.assistant_budget_seconds == 12.5


def test_an_injected_conversation_model_wins_over_the_gemini_key() -> None:
    injected = ScriptedConversationModel()
    settings = Settings(gemini_api_key=SecretStr("key-123"))

    dependencies = build_dependencies(
        settings, quote_repository=FakeQuoteRepository(), conversation_model=injected
    )

    assert dependencies.conversation_model is injected


def test_the_assistant_creates_a_quote_through_the_wired_app_with_recorded_gemini_answers(
    recorded_transport: httpx.MockTransport,
    requests_seen: list[httpx.Request],
) -> None:
    answers = iter(
        [
            (RECORDINGS / "gemini_conversation_function_call.json").read_bytes(),
            # The Quote's Narrative is written by the same Gemini while the tool runs.
            (RECORDINGS / "gemini_generate_content_success.json").read_bytes(),
            (RECORDINGS / "gemini_conversation_text.json").read_bytes(),
        ]
    )

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "generativelanguage.googleapis.com":
            requests_seen.append(request)
            return httpx.Response(200, content=next(answers))
        return recorded_transport.handler(request)  # type: ignore[attr-defined,no-any-return]

    settings = Settings(redis_url=None, gemini_api_key=SecretStr("key-123"))
    dependencies = build_dependencies(
        settings, transport=httpx.MockTransport(upstream), quote_repository=FakeQuoteRepository()
    )
    with TestClient(create_app(settings, dependencies)) as client:
        response = client.post(
            "/assistant/messages",
            json={"messages": [{"role": "user", "content": "Ayşe Yılmaz için teklif: Etimesgut"}]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        stored = client.get(f"/quotes/{body['quote']['id']}").json()

    assert stored["quote_number"] == body["quote"]["quote_number"]
    assert body["reply"].startswith(f"Teklifiniz hazır. {stored['quote_number']} numaralı")
    assert "{" not in body["reply"]
    gemini_requests = [
        r for r in requests_seen if r.url.host == "generativelanguage.googleapis.com"
    ]
    assert len(gemini_requests) == 3
    assert stored["narrative"]["source"] == "llm"
    assert gemini_requests[0].headers["x-goog-api-key"] == "key-123"


def _wired_engine(settings: Settings) -> AsyncEngine:
    dependencies = build_dependencies(settings)
    repository = dependencies.quote_repository
    assert isinstance(repository, PostgresQuoteRepository)
    return repository._engine


def test_the_real_wiring_keeps_a_connection_pool_unless_serverless_turns_it_off() -> None:
    assert isinstance(_wired_engine(Settings()).pool, AsyncAdaptedQueuePool)
    assert isinstance(_wired_engine(Settings(database_client_pool=False)).pool, NullPool)


def test_an_upstash_url_over_tls_is_cached_through_a_tls_connection() -> None:
    settings = Settings(redis_url="rediss://default:token@eu1-demo-12345.upstash.io:6379")

    dependencies = build_dependencies(settings, quote_repository=FakeQuoteRepository())

    geocoder = dependencies.quote_service._geocoder
    assert isinstance(geocoder, CachedGeocoder)
    pool = geocoder._redis.connection_pool
    assert pool.connection_class is SSLConnection
    assert pool.connection_kwargs["host"] == "eu1-demo-12345.upstash.io"
    assert pool.connection_kwargs["password"] == "token"


def test_a_plain_redis_url_stays_unencrypted() -> None:
    settings = Settings(redis_url="redis://redis:6379/0")

    dependencies = build_dependencies(settings, quote_repository=FakeQuoteRepository())

    geocoder = dependencies.quote_service._geocoder
    assert isinstance(geocoder, CachedGeocoder)
    assert geocoder._redis.connection_pool.connection_class is Connection


def test_the_cache_timeout_comes_from_the_settings() -> None:
    settings = Settings(redis_url="rediss://default:token@host:6379", redis_timeout_seconds=1.5)

    dependencies = build_dependencies(settings, quote_repository=FakeQuoteRepository())

    geocoder = dependencies.quote_service._geocoder
    assert isinstance(geocoder, CachedGeocoder)
    kwargs = geocoder._redis.connection_pool.connection_kwargs
    assert (kwargs["socket_connect_timeout"], kwargs["socket_timeout"]) == (1.5, 1.5)


def test_rate_limit_counters_live_in_postgres_without_redis() -> None:
    dependencies = build_dependencies(Settings(redis_url=None))

    assert dependencies.rate_limiter is not None
    assert isinstance(dependencies.rate_limiter._store, PostgresCounterStore)


def test_rate_limit_counters_live_in_redis_when_a_redis_url_is_set() -> None:
    dependencies = build_dependencies(Settings(redis_url="redis://127.0.0.1:6379/0"))

    assert dependencies.rate_limiter is not None
    assert isinstance(dependencies.rate_limiter._store, RedisCounterStore)


def test_an_injected_counter_store_wins() -> None:
    store = InMemoryCounterStore(clock=lambda: datetime.now(UTC))

    dependencies = build_dependencies(
        Settings(redis_url="redis://127.0.0.1:6379/0"),
        quote_repository=FakeQuoteRepository(),
        counter_store=store,
    )

    assert dependencies.rate_limiter is not None
    assert dependencies.rate_limiter._store is store


def test_without_a_database_or_a_counter_store_nothing_is_limited() -> None:
    dependencies = build_dependencies(Settings(), quote_repository=FakeQuoteRepository())

    assert dependencies.rate_limiter is None
