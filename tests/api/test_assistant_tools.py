"""The `create_quote` tool: its schema comes from the POST /quotes request model."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from sunquote.api.assistant_tools import create_quote_declaration, create_quote_request
from sunquote.api.schemas import QuoteRequestBody


def keys_anywhere(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {key for value in node.values() for key in keys_anywhere(value)}
    if isinstance(node, list):
        return {key for item in node for key in keys_anywhere(item)}
    return set()


def arguments() -> dict[str, Any]:
    return {
        "customer": {"name": "Ayşe Yılmaz"},
        "site": {"address": "Etimesgut, Ankara"},
        "roof": {
            "roof_type": "pitched",
            "usable_area_m2": 40,
            "azimuth_deg": 180,
            "tilt_deg": 30,
        },
        "consumption": {"monthly_consumption_kwh": 300},
        "subscriber_group": "residential",
    }


def test_the_tool_is_named_create_quote_and_describes_itself() -> None:
    declaration = create_quote_declaration()

    assert declaration.name == "create_quote"
    assert declaration.description
    assert declaration.parameters["type"] == "object"


def test_the_schema_has_no_coordinates_and_no_exchange_rate_override() -> None:
    schema = create_quote_declaration().parameters

    names = keys_anywhere(schema)
    assert not names & {"latitude", "longitude", "exchange_rate_override"}
    assert "latitude" not in json.dumps(schema)
    assert "exchange_rate_override" not in schema["properties"]


def test_the_address_is_required_and_is_the_only_site_field() -> None:
    site = create_quote_declaration().parameters["properties"]["site"]

    assert site["required"] == ["address"]
    assert set(site["properties"]) == {"address"}
    assert site["properties"]["address"]["type"] == "string"


def test_the_schema_is_flat_json_schema_the_model_can_read() -> None:
    schema = create_quote_declaration().parameters
    text = json.dumps(schema)

    assert "$ref" not in text
    assert "$defs" not in text
    assert "anyOf" not in text
    roof = schema["properties"]["roof"]["properties"]
    assert roof["roof_type"]["enum"] == ["pitched", "flat"]
    assert roof["usable_area_m2"]["type"] == "number"
    assert roof["azimuth_deg"]["type"] == "number"
    assert set(schema["required"]) == {
        "customer",
        "site",
        "roof",
        "consumption",
        "subscriber_group",
    }
    assert schema["properties"]["customer"]["required"] == ["name"]


def test_the_schema_keeps_the_request_models_field_descriptions() -> None:
    schema = create_quote_declaration().parameters

    assert (
        "Compass bearing"
        in schema["properties"]["roof"]["properties"]["azimuth_deg"]["description"]
    )


def test_valid_arguments_become_the_quote_request_body() -> None:
    body = create_quote_request(arguments())

    assert isinstance(body, QuoteRequestBody)
    assert body.customer.name == "Ayşe Yılmaz"
    assert body.site.address == "Etimesgut, Ankara"
    assert body.site.coordinates() is None


def test_coordinates_and_an_exchange_rate_the_model_supplied_anyway_are_dropped() -> None:
    given = arguments()
    given["site"].update({"latitude": 1, "longitude": 2})
    given["exchange_rate_override"] = {"rate": 1, "date": "2026-11-24"}

    body = create_quote_request(given)

    assert body.site.coordinates() is None
    assert body.exchange_rate_override is None
    assert body.site.address == "Etimesgut, Ankara"


def test_coordinates_cannot_stand_in_for_a_missing_address() -> None:
    given = arguments()
    given["site"] = {"latitude": 39.9, "longitude": 32.8}

    with pytest.raises(ValidationError) as error:
        create_quote_request(given)

    assert [item["loc"] for item in error.value.errors()] == [("site", "address")]


def test_arguments_the_request_model_rejects_raise_its_validation_error() -> None:
    given = arguments()
    given["roof"]["tilt_deg"] = 120
    del given["customer"]

    with pytest.raises(ValidationError) as error:
        create_quote_request(given)

    assert {item["loc"] for item in error.value.errors()} == {
        ("customer",),
        ("roof", "tilt_deg"),
    }
