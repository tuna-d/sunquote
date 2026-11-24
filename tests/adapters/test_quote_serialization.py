"""The JSON form a Quote is stored in, checked without a database."""

import json
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sunquote.adapters.postgres.quote_repository import quote_from_json, quote_to_json
from sunquote.domain.narrative import NarrativeDraft, NarrativeRecord, NarrativeSource
from sunquote.domain.quote import Quote, build_quote
from tests.factories import (
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_exchange_rate,
    make_reference_data,
    make_request,
    make_specific_yield,
)
from tests.fakes import FakeGeocoder


def build(monthly_consumption_kwh: str) -> Quote:
    return build_quote(
        request=make_request(monthly_consumption_kwh=monthly_consumption_kwh),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )


def field_names(value: Any) -> set[str]:
    """Every dataclass field name anywhere in `value`."""
    names: set[str] = set()
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            names.add(field.name)
            names |= field_names(getattr(value, field.name))
    elif isinstance(value, tuple | list):
        for item in value:
            names |= field_names(item)
    return names


def keys(document: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(document, dict):
        for key, value in document.items():
            found.add(key)
            found |= keys(value)
    elif isinstance(document, list):
        for item in document:
            found |= keys(item)
    return found


def test_a_quote_survives_the_trip_through_json_text() -> None:
    quote = build("500")  # two System Options, with savings and cash flows

    restored = quote_from_json(json.loads(json.dumps(quote_to_json(quote))))

    assert len(quote.system_options) == 2
    assert restored == quote


def test_every_field_of_the_quote_is_in_the_stored_document() -> None:
    quote = build("500")

    assert field_names(quote) <= keys(quote_to_json(quote))


def test_decimals_are_stored_as_strings_so_no_figure_becomes_a_float() -> None:
    document = quote_to_json(build("500"))

    assert document["assumptions"]["exchange_rate"]["rate"] == "40"
    assert document["valid_until"] == "2026-12-09"


def test_quotes_stored_before_geocoding_can_still_be_read() -> None:
    quote = build("500")
    document = quote_to_json(quote)
    del document["assumptions"]["geocoding_result"]
    del document["assumptions"]["submitted_request"]["site"]["address"]

    assert quote_from_json(document) == quote


def test_the_submitted_address_and_resolved_match_survive_storage() -> None:
    base = build("500")
    request = base.assumptions.submitted_request
    site = replace(request.site, address="An\u0131tkabir, Ankara", coordinates=None)
    quote = replace(
        base,
        assumptions=replace(
            base.assumptions,
            submitted_request=replace(request, site=site),
            geocoding_result=FakeGeocoder().result,
        ),
    )

    assert quote_from_json(quote_to_json(quote)) == quote


def with_llm_narrative(quote: Quote) -> Quote:
    record = NarrativeRecord(
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
    return replace(quote, narrative=record)


def test_the_narrative_record_survives_the_trip_through_json_text() -> None:
    quote = with_llm_narrative(build("500"))

    restored = quote_from_json(json.loads(json.dumps(quote_to_json(quote))))

    assert restored == quote
    assert restored.narrative.draft is not None
    assert restored.narrative.generated_at == datetime(2026, 11, 24, 9, 30, tzinfo=UTC)


def test_a_fallback_narrative_survives_the_trip_through_json_text() -> None:
    fallback = NarrativeRecord(
        source=NarrativeSource.FALLBACK,
        draft=None,
        model=None,
        generated_at=datetime(2026, 11, 24, 9, 30, tzinfo=UTC),
    )
    quote = replace(build("500"), narrative=fallback)

    assert quote_from_json(json.loads(json.dumps(quote_to_json(quote)))) == quote


def test_quotes_stored_before_the_narrative_step_read_back_as_fallback() -> None:
    quote = with_llm_narrative(build("500"))
    document = quote_to_json(quote)
    del document["narrative"]

    restored = quote_from_json(document)

    assert restored.narrative.source is NarrativeSource.FALLBACK
    assert restored.narrative.draft is None
    assert restored.narrative.model is None
    assert restored.narrative.generated_at is None
    assert restored == replace(quote, narrative=restored.narrative)
