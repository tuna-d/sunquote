"""The Postgres quote repository against a real Postgres.

These tests need a database. Point `SUNQUOTE_TEST_DATABASE_URL` at one, for example the
Compose service published on localhost:

    SUNQUOTE_TEST_DATABASE_URL=postgresql+asyncpg://sunquote:sunquote@localhost:5432/sunquote

Without that variable, or when the database cannot be reached, the tests are skipped (in CI,
where `CI=true`, an unreachable database fails them instead). Every test works in its own
temporary schema, so the database's own data is never touched.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from alembic import command
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from sunquote.adapters.postgres.migrate import alembic_config, upgrade_to_head
from sunquote.adapters.postgres.quote_repository import PostgresQuoteRepository, quote_to_json
from sunquote.adapters.postgres.tables import metadata, quotes
from sunquote.api.app import create_app
from sunquote.api.dependencies import AppDependencies
from sunquote.config import Settings
from sunquote.demo import seed
from sunquote.domain.model import GeocodingResult, RoofType
from sunquote.domain.narrative import NarrativeDraft, NarrativeRecord, NarrativeSource
from sunquote.domain.quote import Quote, build_quote
from sunquote.domain.service import QuoteService
from tests.factories import (
    QUOTE_DATE,
    make_assumptions,
    make_exchange_rate,
    make_reference_data,
    make_request,
    make_specific_yield,
)
from tests.fakes import (
    FakeExchangeRateProvider,
    FakeGeocoder,
    FakeSpecificYieldProvider,
    FixedClock,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def repository(engine: AsyncEngine) -> PostgresQuoteRepository:
    return PostgresQuoteRepository(engine)


def make_quote(quote_number: str = "SQ-2026-000001", customer_name: str = "Şule Öztürk") -> Quote:
    request = make_request()
    return build_quote(
        request=replace(request, customer=replace(request.customer, name=customer_name)),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=quote_number,
    )


async def test_a_stored_quote_comes_back_equal_to_what_was_saved(
    repository: PostgresQuoteRepository,
) -> None:
    quote = make_quote()

    saved = await repository.save(quote)
    fetched = await repository.get(saved.id)

    assert fetched == saved
    assert fetched is not None
    assert fetched.quote == quote  # every Decimal, date, enum and nested object survives
    assert fetched.quote.system_options[0].price.total == quote.system_options[0].price.total
    assert fetched.created_at.tzinfo is not None
    assert (fetched.district, fetched.province) == (None, None)


async def test_district_and_province_are_stored_when_given(
    repository: PostgresQuoteRepository,
) -> None:
    saved = await repository.save(make_quote(), district="Çankaya", province="Ankara")

    fetched = await repository.get(saved.id)

    assert fetched is not None
    assert (fetched.district, fetched.province) == ("Çankaya", "Ankara")


async def test_demo_reset_keeps_samples_and_removes_other_quotes(
    repository: PostgresQuoteRepository,
) -> None:
    sample_number = await repository.next_quote_number(2026)
    visitor_number = await repository.next_quote_number(2026)
    sample = await repository.save(make_quote(sample_number), is_sample=True)
    visitor = await repository.save(make_quote(visitor_number))

    assert await repository.delete_non_sample_quotes() == 1
    assert await repository.delete_non_sample_quotes() == 0
    assert (await repository.list_newest_first(page=1, page_size=10)).items == (sample,)
    assert await repository.get(sample.id) == sample
    assert await repository.get(visitor.id) is None
    assert await repository.next_quote_number(2026) == "SQ-2026-000003"


async def test_demo_seed_creates_six_varied_samples_once(
    repository: PostgresQuoteRepository,
) -> None:
    class DemoGeocoder(FakeGeocoder):
        async def geocode(self, address: str) -> GeocodingResult:
            return replace(await super().geocode(address), province=address.split(", ")[-1])

    geocoder = DemoGeocoder()
    service = QuoteService(
        quote_repository=repository,
        geocoder=geocoder,
        specific_yield_provider=FakeSpecificYieldProvider(),
        exchange_rate_provider=FakeExchangeRateProvider(),
        clock=FixedClock(),
        reference_data=make_reference_data(assumptions=make_assumptions(dc_ac_ratio_max="1.50")),
    )

    await seed(repository, service)
    first = await repository.list_newest_first(page=1, page_size=10)
    await seed(repository, service)

    assert first.total == 6
    assert all(item.is_sample for item in first.items)
    assert {item.province for item in first.items} == {"Ankara", "İzmir", "Antalya"}
    assert {item.quote.assumptions.roof_type for item in first.items} == {
        RoofType.FLAT,
        RoofType.PITCHED,
    }
    assert {len(item.quote.system_options) for item in first.items} == {1, 2}
    assert {item.quote.assumptions.consumption_derived_from_bill for item in first.items} == {
        True,
        False,
    }
    assert await repository.list_newest_first(page=1, page_size=10) == first
    assert len(geocoder.addresses) == 6

    app = create_app(
        Settings(), AppDependencies(quote_service=service, quote_repository=repository)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        items = (await client.get("/quotes")).json()["items"]
        assert len(items) == 6
        assert all(item["is_sample"] is True for item in items)
        response = await client.get(f"/quotes/{first.items[0].id}")
        assert response.status_code == 200
        assert response.json()["is_sample"] is True


async def test_concurrent_sample_saves_keep_one_immutable_quote(
    repository: PostgresQuoteRepository,
) -> None:
    numbers = [await repository.next_quote_number(2026) for _ in range(2)]

    first, second = await asyncio.gather(
        *(repository.save(make_quote(number), is_sample=True) for number in numbers)
    )

    assert first == second
    assert (await repository.list_newest_first(page=1, page_size=10)).items == (first,)


async def test_the_whole_quote_is_in_one_jsonb_column_next_to_the_listing_columns(
    repository: PostgresQuoteRepository, engine: AsyncEngine
) -> None:
    saved = await repository.save(make_quote("SQ-2026-000007", "Mehmet Kaya"))

    async with engine.connect() as connection:
        row = (await connection.execute(select(quotes))).one()

    assert row.id == saved.id
    assert row.quote_number == "SQ-2026-000007"
    assert row.customer_name == "Mehmet Kaya"
    assert row.created_at == saved.created_at
    assert row.quote["valid_until"] == "2026-12-09"
    assert row.quote["customer"]["name"] == "Mehmet Kaya"
    assert row.quote["assumptions"]["exchange_rate"]["rate"] == "40"  # a string, never a float


async def test_an_unknown_id_is_not_found(repository: PostgresQuoteRepository) -> None:
    assert await repository.get(uuid4()) is None


async def test_quote_numbers_count_up_from_one(repository: PostgresQuoteRepository) -> None:
    numbers = [await repository.next_quote_number(2026) for _ in range(3)]

    assert numbers == ["SQ-2026-000001", "SQ-2026-000002", "SQ-2026-000003"]


async def test_the_sequence_restarts_each_year(repository: PostgresQuoteRepository) -> None:
    numbers = [
        await repository.next_quote_number(2026),
        await repository.next_quote_number(2026),
        await repository.next_quote_number(2027),
        await repository.next_quote_number(2026),
        await repository.next_quote_number(2027),
    ]

    assert numbers == [
        "SQ-2026-000001",
        "SQ-2026-000002",
        "SQ-2027-000001",
        "SQ-2026-000003",
        "SQ-2027-000002",
    ]


async def test_concurrent_creation_gives_unique_consecutive_numbers(
    repository: PostgresQuoteRepository,
) -> None:
    count = 25

    numbers = await asyncio.gather(*(repository.next_quote_number(2026) for _ in range(count)))

    assert sorted(numbers) == [f"SQ-2026-{sequence:06d}" for sequence in range(1, count + 1)]


async def test_concurrent_saves_of_numbered_quotes_all_succeed(
    repository: PostgresQuoteRepository,
) -> None:
    async def create(index: int) -> str:
        number = await repository.next_quote_number(2026)
        saved = await repository.save(make_quote(number, f"Customer {index}"))
        return saved.quote.quote_number

    numbers = await asyncio.gather(*(create(index) for index in range(10)))

    assert len(set(numbers)) == 10
    assert (await repository.list_newest_first(page=1, page_size=50)).total == 10


async def test_the_list_is_newest_first_with_pages_and_a_total(
    repository: PostgresQuoteRepository,
) -> None:
    for index in range(1, 6):
        number = await repository.next_quote_number(2026)
        await repository.save(make_quote(number, f"Customer {index}"))

    first = await repository.list_newest_first(page=1, page_size=2)
    second = await repository.list_newest_first(page=2, page_size=2)
    last = await repository.list_newest_first(page=3, page_size=2)
    beyond = await repository.list_newest_first(page=4, page_size=2)

    names = [
        [stored.quote.customer.name for stored in page.items]
        for page in (first, second, last, beyond)
    ]
    assert names == [["Customer 5", "Customer 4"], ["Customer 3", "Customer 2"], ["Customer 1"], []]
    assert {page.total for page in (first, second, last, beyond)} == {5}
    assert first.items[0].quote.valid_until == date(2026, 12, 9)
    assert first.items[0].quote.system_options[0].capacity_kwp == Decimal("4.0")


async def test_a_quote_number_cannot_be_stored_twice(
    repository: PostgresQuoteRepository,
) -> None:
    await repository.save(make_quote("SQ-2026-000001"))

    with pytest.raises(IntegrityError):
        await repository.save(make_quote("SQ-2026-000001", "Someone Else"))

    page = await repository.list_newest_first(page=1, page_size=10)
    assert [stored.quote.customer.name for stored in page.items] == ["Şule Öztürk"]


async def test_the_migrations_create_the_schema_the_tables_describe(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {
                table: {
                    column["name"]: column for column in inspect(sync_connection).get_columns(table)
                }
                for table in metadata.tables
            }
        )

    for table in metadata.tables.values():
        assert set(columns[table.name]) == {column.name for column in table.columns}, table.name
        for column in table.columns:
            assert columns[table.name][column.name]["nullable"] == column.nullable, column.name


async def test_running_the_migrations_again_changes_nothing(
    repository: PostgresQuoteRepository, engine: AsyncEngine
) -> None:
    saved = await repository.save(make_quote())

    await upgrade_to_head(engine)

    assert await repository.get(saved.id) == saved


async def test_the_sample_migration_preserves_an_older_quote_as_non_sample(
    repository: PostgresQuoteRepository, engine: AsyncEngine
) -> None:
    quote_id = uuid4()
    quote = make_quote()
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: command.downgrade(alembic_config(conn), "0001"))
        await connection.execute(
            insert(quotes).values(
                id=quote_id,
                quote_number=quote.quote_number,
                customer_name=quote.customer.name,
                quote=quote_to_json(quote),
            )
        )

    await upgrade_to_head(engine)

    stored = await repository.get(quote_id)
    assert stored is not None
    assert stored.is_sample is False
    assert stored.quote == quote


def narrative_record() -> NarrativeRecord:
    return NarrativeRecord(
        source=NarrativeSource.LLM,
        draft=NarrativeDraft(
            greeting="Sayın {customer_name},",
            summary="Sistem {option_1_capacity_kwp} kWp gücündedir.",
            next_steps="Teklif {valid_until} tarihine kadar geçerlidir.",
            options_comparison="{option_1_total_try} ile {option_2_total_try}.",
        ),
        model="gemini-test",
        generated_at=datetime(2026, 11, 24, 9, 30, tzinfo=UTC),
    )


async def test_the_narrative_record_round_trips_with_the_quote(
    repository: PostgresQuoteRepository,
) -> None:
    quote = replace(make_quote(), narrative=narrative_record())

    saved = await repository.save(quote)
    fetched = await repository.get(saved.id)

    assert fetched is not None
    assert fetched.quote.narrative == narrative_record()
    assert fetched.quote == quote


async def test_a_quote_stored_without_a_narrative_reads_back_as_fallback(
    repository: PostgresQuoteRepository, engine: AsyncEngine
) -> None:
    saved = await repository.save(make_quote())
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE quotes SET quote = quote - 'narrative' WHERE id = :id"), {"id": saved.id}
        )

    fetched = await repository.get(saved.id)

    assert fetched is not None
    assert fetched.quote.narrative.source is NarrativeSource.FALLBACK
    assert fetched.quote.narrative.draft is None
    assert fetched.quote.narrative.generated_at is None
