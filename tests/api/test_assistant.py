"""POST /assistant/messages through the real app with a scripted fake conversation model.

The default arguments give the same Quote as tests/api/test_quotes.py: two System Options. What
reaches the Sales Rep is the response; the tests assert on it and on the Quotes stored, not on
the prompt's wording.
"""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sunquote.api import turkish
from sunquote.domain.conversation import TextReply, ToolCall
from sunquote.domain.errors import AddressNotFoundError, ConversationUnavailableError
from sunquote.domain.narrative import ViolationKind
from tests.conftest import ClientFactory
from tests.fakes import FakeGeocoder, FakeQuoteRepository, FakeSpecificYieldProvider
from tests.fakes import ScriptedConversationModel as Script

PROBLEM_JSON = "application/problem+json"
URN = "urn:sunquote:problem:"

MESSAGE = (
    "Ayşe Yılmaz için teklif: Etimesgut, Ankara. 40 m² eğimli çatı, güneye bakıyor, 30 derece. "
    "Aylık 500 kWh tüketiyor."
)
REPLY = (
    "Teklifiniz hazır. {quote_number} numaralı teklifte ilk seçenek {option_1_capacity_kwp} kWp "
    "gücündedir ve KDV dahil {option_1_total_try} tutarındadır."
)


def quote_arguments() -> dict[str, Any]:
    return {
        "customer": {"name": "Ayşe Yılmaz"},
        "site": {"address": "Etimesgut, Ankara"},
        "roof": {
            "roof_type": "pitched",
            "usable_area_m2": 40,
            "azimuth_deg": 180,
            "tilt_deg": 30,
        },
        "consumption": {"monthly_consumption_kwh": 500},
        "subscriber_group": "residential",
    }


def create(**changes: Any) -> ToolCall:
    arguments = quote_arguments()
    for path, value in changes.items():
        *parents, leaf = path.split("__")
        target = arguments
        for key in parents:
            target = target[key]
        target[leaf] = value
    return ToolCall("create_quote", arguments)


def conversation(content: str = MESSAGE) -> dict[str, Any]:
    return {"messages": [{"role": "user", "content": content}]}


def ask(client: TestClient, body: dict[str, Any] | None = None) -> Any:
    return client.post("/assistant/messages", json=conversation() if body is None else body)


def client_with(client_factory: ClientFactory, model: Script, **options: Any) -> TestClient:
    return client_factory(conversation_model=model, **options)


# --- A complete message creates a Quote ------------------------------------------------------


def test_a_complete_message_creates_one_stored_quote_and_returns_its_reference(
    client_factory: ClientFactory,
    quote_repository: FakeQuoteRepository,
    geocoder: FakeGeocoder,
) -> None:
    client = client_with(client_factory, Script(create(), TextReply(REPLY)))

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    (stored,) = quote_repository.stored
    assert body["quote"] == {
        "id": str(stored.id),
        "quote_number": stored.quote.quote_number,
        "document_url": f"http://testserver/quotes/{stored.id}/document",
    }
    assert body["missing_fields"] == []
    assert geocoder.addresses == ["Etimesgut, Ankara"]
    assert stored.quote.customer.name == "Ayşe Yılmaz"
    assert client.get(f"/quotes/{stored.id}/document").status_code == 200
    assert (
        client.get(f"/quotes/{stored.id}").json()["quote_number"] == body["quote"]["quote_number"]
    )


def test_the_reply_has_every_placeholder_filled_from_the_quote(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script(create(), TextReply(REPLY)))

    body = ask(client).json()

    quote = client.get(f"/quotes/{body['quote']['id']}").json()
    first = quote["system_options"][0]
    capacity = turkish.format_decimal(Decimal(str(first["capacity_kwp"])).quantize(Decimal("0.01")))
    total = turkish.format_try(first["price"]["total_try"])
    assert body["reply"] == (
        f"Teklifiniz hazır. {quote['quote_number']} numaralı teklifte ilk seçenek {capacity} kWp "
        f"gücündedir ve KDV dahil {total} tutarındadır."
    )
    assert "{" not in body["reply"]


def test_the_model_gets_the_conversation_the_tool_and_then_the_quotes_placeholders(
    client_factory: ClientFactory,
) -> None:
    model = Script(create(), TextReply(REPLY))
    client = client_with(client_factory, model)
    history = {
        "messages": [
            {"role": "user", "content": "Ayşe Yılmaz için teklif"},
            {"role": "assistant", "content": "Çatı bilgisi nedir?"},
            {"role": "user", "content": "40 m², güney, 30 derece, 500 kWh, Etimesgut"},
        ]
    }

    ask(client, history)

    first, second = model.calls
    assert [(m.role.value, m.content) for m in first.messages] == [
        (m["role"], m["content"]) for m in history["messages"]
    ]
    assert [tool.name for tool in first.tools] == ["create_quote"]
    assert first.exchanges == ()
    assert first.rejected_reply is None
    assert "Turkish" in first.system_instruction
    (exchange,) = second.exchanges
    assert exchange.call.name == "create_quote"
    assert exchange.result["status"] == "created"
    placeholders = exchange.result["available_placeholders"]
    assert "option_1_total_try" in placeholders
    assert "option_2_total_try" in placeholders
    assert "customer_name" in placeholders
    # The model is told which placeholders exist, never a figure.
    assert "Ayşe" not in str(exchange.result)


def test_the_server_keeps_no_conversation_state(client_factory: ClientFactory) -> None:
    model = Script(create(), TextReply(REPLY), create(), TextReply(REPLY))
    client = client_with(client_factory, model)

    ask(client, conversation("birinci"))
    ask(client, conversation("ikinci"))

    first_request, _, second_request, _ = model.calls
    assert [m.content for m in first_request.messages] == ["birinci"]
    assert [m.content for m in second_request.messages] == ["ikinci"]
    assert second_request.exchanges == ()


def test_a_text_answer_without_a_quote_is_returned_as_it_is(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    client = client_with(client_factory, Script(TextReply("Hangi ilde oturuyorlar?")))

    body = ask(client).json()

    assert body == {"reply": "Hangi ilde oturuyorlar?", "quote": None, "missing_fields": []}
    assert quote_repository.stored == []


def test_coordinates_the_model_supplies_are_ignored_and_the_address_is_geocoded(
    client_factory: ClientFactory,
    geocoder: FakeGeocoder,
    specific_yield_provider: FakeSpecificYieldProvider,
) -> None:
    sneaky = create(site__latitude=1.5, site__longitude=2.5)
    client = client_with(client_factory, Script(sneaky, TextReply(REPLY)))

    assert ask(client).status_code == 200

    assert geocoder.addresses == ["Etimesgut, Ankara"]
    (query,) = specific_yield_provider.queries
    assert query.coordinates == geocoder.result.coordinates


# --- The reply after a Quote is checked ------------------------------------------------------


def test_a_reply_with_a_stray_figure_gets_one_retry_with_the_violations(
    client_factory: ClientFactory,
) -> None:
    model = Script(create(), TextReply("Sistem 8,4 kWp gücündedir."), TextReply(REPLY))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert body["reply"].startswith("Teklifiniz hazır. SQ-")
    assert len(model.calls) == 3
    retry = model.calls[2]
    assert retry.rejected_reply is not None
    assert retry.rejected_reply.text == "Sistem 8,4 kWp gücündedir."
    assert [v.kind for v in retry.rejected_reply.violations] == [
        ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER
    ]
    assert len(retry.exchanges) == 1


@pytest.mark.parametrize(
    "bad_reply",
    [
        "Toplam 106.000 TL.",
        "Fiyat {option_9_total_try} olur.",
        "Fiyat {option_1_price} olur.",
        "{ eksik",
        "a" * 1501,
    ],
    ids=["digit", "unavailable", "unknown", "unbalanced", "too-long"],
)
def test_a_reply_that_stays_invalid_is_replaced_by_the_fixed_confirmation(
    client_factory: ClientFactory, bad_reply: str
) -> None:
    model = Script(create(), TextReply(bad_reply), TextReply(bad_reply))
    client = client_with(client_factory, model)

    body = ask(client).json()

    quote = client.get(f"/quotes/{body['quote']['id']}").json()
    reply = body["reply"]
    assert len(model.calls) == 3
    assert quote["quote_number"] in reply
    assert body["quote"]["document_url"] in reply
    for option in quote["system_options"]:
        capacity = turkish.format_decimal(
            Decimal(str(option["capacity_kwp"])).quantize(Decimal("0.01"))
        )
        assert f"{capacity} kWp" in reply
        assert turkish.format_try(option["price"]["total_try"]) in reply
    assert "{" not in reply
    assert bad_reply not in reply


def test_the_fixed_confirmation_of_a_single_option_quote_lists_that_option(
    client_factory: ClientFactory,
) -> None:
    model = Script(create(roof__usable_area_m2=20), TextReply("8"), TextReply("8"))
    client = client_with(client_factory, model)

    body = ask(client).json()

    quote = client.get(f"/quotes/{body['quote']['id']}").json()
    assert len(quote["system_options"]) == 1
    assert turkish.format_try(quote["system_options"][0]["price"]["total_try"]) in body["reply"]


# --- The tool loop ---------------------------------------------------------------------------


def test_a_second_create_quote_gets_a_tool_error_and_creates_nothing(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    model = Script(create(), create(), TextReply(REPLY))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert len(quote_repository.stored) == 1
    assert body["quote"]["id"] == str(quote_repository.stored[0].id)
    assert body["reply"].startswith("Teklifiniz hazır.")
    _, _, third = model.calls
    first_exchange, second_exchange = third.exchanges
    assert first_exchange.result["status"] == "created"
    assert second_exchange.result["error"]["type"].endswith("quote-already-created")


def test_the_loop_stops_after_three_model_calls_and_confirms_the_quote(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    model = Script(create(), create(), create(), TextReply(REPLY))
    client = client_with(client_factory, model)

    response = ask(client)

    assert response.status_code == 200
    assert len(model.calls) == 3
    body = response.json()
    assert len(quote_repository.stored) == 1
    assert body["quote"]["quote_number"] in body["reply"]
    assert "{" not in body["reply"]


def test_a_loop_that_never_creates_a_quote_ends_as_unavailable_after_three_calls(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    bad = create(roof__tilt_deg=120)
    model = Script(bad, bad, bad, TextReply("hiç okunmaz"))
    client = client_with(client_factory, model)

    response = ask(client)

    assert len(model.calls) == 3
    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"] == f"{URN}assistant-unavailable"
    assert quote_repository.stored == []


def test_a_confirmation_follows_when_the_time_budget_runs_out_after_a_quote(
    client_factory: ClientFactory,
) -> None:
    model = Script(create(), 5.0)
    client = client_with(client_factory, model, assistant_budget_seconds=0.3)

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["quote"]["quote_number"] in body["reply"]


def test_the_time_budget_running_out_before_any_quote_is_unavailable(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script(5.0), assistant_budget_seconds=0.2)

    response = ask(client)

    assert response.status_code == 503
    assert response.json()["type"] == f"{URN}assistant-unavailable"


# --- Tool errors -----------------------------------------------------------------------------


def test_invalid_arguments_come_back_to_the_model_as_a_tool_error_naming_the_field(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    model = Script(create(roof__tilt_deg=120), create(), TextReply(REPLY))
    client = client_with(client_factory, model)

    ask(client)

    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}validation-error"
    assert [item["field"] for item in error["errors"]] == ["roof.tilt_deg"]
    assert len(quote_repository.stored) == 1


def test_an_address_the_geocoder_cannot_find_is_a_tool_error_and_stores_nothing(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository, geocoder: FakeGeocoder
) -> None:
    geocoder.error = AddressNotFoundError()
    model = Script(create(), TextReply("Adresi bulamadım."))
    client = client_with(client_factory, model)

    ask(client)

    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}address-not-found"
    assert quote_repository.stored == []


# --- Errors ----------------------------------------------------------------------------------


def test_without_a_conversation_model_the_assistant_is_not_configured_and_the_rest_works(
    client: TestClient,
) -> None:
    response = ask(client)

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert problem["type"] == f"{URN}assistant-not-configured"
    assert problem["status"] == 503
    assert client.get("/health").status_code == 200
    assert client.get("/quotes").status_code == 200


def test_an_unavailable_model_before_any_quote_is_a_503_and_stores_nothing(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    client = client_with(client_factory, Script(ConversationUnavailableError("HTTP 429")))

    response = ask(client)

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"] == f"{URN}assistant-unavailable"
    assert quote_repository.stored == []


def test_an_unavailable_model_after_a_quote_is_the_fixed_confirmation_with_200(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    model = Script(create(), ConversationUnavailableError("HTTP 500"))
    client = client_with(client_factory, model)

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    (stored,) = quote_repository.stored
    assert body["quote"]["id"] == str(stored.id)
    assert stored.quote.quote_number in body["reply"]
    assert body["quote"]["document_url"] in body["reply"]


# --- The request -----------------------------------------------------------------------------


def valid_messages(count: int) -> list[dict[str, str]]:
    roles = ["assistant", "user"] * 10
    messages = [{"role": roles[i % 2], "content": f"mesaj {i}"} for i in range(count)]
    messages[-1]["role"] = "user"
    return messages


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "messages"),
        ({"messages": []}, "messages"),
        ({"messages": valid_messages(21)}, "messages"),
        ({"messages": [{"role": "assistant", "content": "Merhaba"}]}, "messages"),
        (
            {
                "messages": [
                    {"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                ]
            },
            "messages",
        ),
        ({"messages": [{"role": "user", "content": "a" * 2001}]}, "messages.0.content"),
        ({"messages": [{"role": "user", "content": ""}]}, "messages.0.content"),
        ({"messages": [{"role": "system", "content": "a"}]}, "messages.0.role"),
        ({"messages": [{"role": "user"}]}, "messages.0.content"),
        ({"messages": "merhaba"}, "messages"),
    ],
    ids=[
        "missing",
        "empty",
        "21-messages",
        "only-an-assistant-message",
        "last-is-assistant",
        "content-too-long",
        "empty-content",
        "unknown-role",
        "no-content",
        "not-a-list",
    ],
)
def test_a_bad_request_is_a_422_problem_naming_the_field(
    client_factory: ClientFactory, body: dict[str, Any], field: str
) -> None:
    model = Script()
    client = client_with(client_factory, model)

    response = ask(client, body)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert problem["type"] == f"{URN}validation-error"
    assert [item["field"] for item in problem["errors"]] == [field]
    assert model.calls == []


def test_twenty_messages_of_two_thousand_characters_are_accepted(
    client_factory: ClientFactory,
) -> None:
    messages = valid_messages(20)
    messages[0]["content"] = "a" * 2000
    client = client_with(client_factory, Script(TextReply("Tamam.")))

    assert ask(client, {"messages": messages}).status_code == 200


# --- Documentation ---------------------------------------------------------------------------


def test_the_openapi_description_says_messages_are_sent_to_gemini(client: TestClient) -> None:
    schema = deepcopy(client.get("/openapi.json").json())

    operation = schema["paths"]["/assistant/messages"]["post"]
    description = operation["description"]
    assert "Gemini" in description
    assert "training" in description
    assert "Address" in description
    assert "503" in operation["responses"]
    assert "422" in operation["responses"]
