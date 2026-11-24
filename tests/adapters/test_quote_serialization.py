"""The JSON form a Quote is stored in, checked without a database."""

import json
from dataclasses import fields, is_dataclass, replace
from typing import Any

from sunquote.adapters.postgres.quote_repository import quote_from_json, quote_to_json
from sunquote.domain.quote import Quote, build_quote
from tests.factories import (
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_assumptions,
    make_catalog,
    make_exchange_rate,
    make_financial_assumptions,
    make_pricing_assumptions,
    make_request,
    make_specific_yield,
    make_tariff,
)
from tests.fakes import FakeGeocoder


def build(monthly_consumption_kwh: str) -> Quote:
    return build_quote(
        request=make_request(monthly_consumption_kwh=monthly_consumption_kwh),
        specific_yield=make_specific_yield(),
        catalog=make_catalog(),
        assumptions=make_assumptions(),
        pricing=make_pricing_assumptions(),
        exchange_rate=make_exchange_rate(),
        tariff=make_tariff(),
        financial=make_financial_assumptions(),
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
