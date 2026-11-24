"""POST /assistant/messages when information is missing or a Quote cannot be created.

Same seam as tests/api/test_assistant.py: the real app, a scripted fake conversation model, and
assertions on the response, the Quotes stored and what the model was told, never on the prompt's
wording.
"""

from typing import Any

import pytest

from sunquote.api.assistant_tools import ask_for_missing_fields_declaration
from sunquote.domain.conversation import TextReply, ToolCall
from sunquote.domain.errors import (
    AddressNotFoundError,
    ConversationUnavailableError,
    LocationNotSupportedError,
    UpstreamUnavailableError,
)
from tests.api.test_assistant import REPLY, URN, ask, client_with, conversation, create
from tests.conftest import ClientFactory
from tests.fakes import FakeGeocoder, FakeQuoteRepository, FakeSpecificYieldProvider
from tests.fakes import ScriptedConversationModel as Script

ASK = "ask_for_missing_fields"
ALL_FIELDS = [
    "customer.name",
    "site.address",
    "roof.roof_type",
    "roof.tilt_deg",
    "roof.azimuth_deg",
    "roof.usable_area_m2",
    "consumption",
    "subscriber_group",
]


def asking(*fields: str, question: str = "Eksik bilgileri yazar mısınız?") -> ToolCall:
    return ToolCall(ASK, {"fields": list(fields), "question": question})


def conversation_of(*messages: tuple[str, str]) -> dict[str, Any]:
    return {"messages": [{"role": role, "content": content} for role, content in messages]}


# --- Asking for what is missing --------------------------------------------------------------


def test_missing_fields_give_the_question_as_the_reply_and_store_nothing(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    question = "Müşterinin adı ve çatının eğimi nedir?"
    model = Script(asking("customer.name", "roof.tilt_deg", question=question))
    client = client_with(client_factory, model)

    response = ask(client)

    assert response.status_code == 200
    assert response.json() == {
        "reply": question,
        "quote": None,
        "missing_fields": ["customer.name", "roof.tilt_deg"],
    }
    assert len(model.calls) == 1
    assert quote_repository.stored == []


def test_the_model_can_choose_between_creating_a_quote_and_asking(
    client_factory: ClientFactory,
) -> None:
    model = Script(asking("consumption"))
    client = client_with(client_factory, model)

    ask(client)

    assert [tool.name for tool in model.calls[0].tools] == ["create_quote", ASK]


def test_the_ask_tool_offers_exactly_the_create_quote_field_paths() -> None:
    parameters = ask_for_missing_fields_declaration().parameters

    assert parameters["properties"]["fields"]["items"]["enum"] == ALL_FIELDS
    assert set(parameters["required"]) == {"fields", "question"}


@pytest.mark.parametrize("bad", [[], ["roof.slope"], ["consumption", "roof"]])
def test_an_ask_with_unknown_or_no_fields_is_a_tool_error_the_model_can_correct(
    client_factory: ClientFactory, bad: list[str]
) -> None:
    model = Script(
        ToolCall(ASK, {"fields": bad, "question": "Eğim nedir?"}),
        asking("roof.tilt_deg", question="Eğim nedir?"),
    )
    client = client_with(client_factory, model)

    body = ask(client).json()

    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}validation-error"
    assert error["errors"][0]["field"].startswith("fields")
    assert body["missing_fields"] == ["roof.tilt_deg"]
    assert body["reply"] == "Eğim nedir?"


def test_an_ask_after_a_quote_exists_is_a_tool_error(client_factory: ClientFactory) -> None:
    model = Script(create(), asking("roof.tilt_deg"), TextReply(REPLY))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert body["missing_fields"] == []
    assert body["quote"] is not None
    error = model.calls[2].exchanges[1].result["error"]
    assert error["type"] == f"{URN}quote-already-created"


# --- Multi-message conversations -------------------------------------------------------------


def test_a_three_message_conversation_ends_in_one_quote_from_every_message(
    client_factory: ClientFactory,
    quote_repository: FakeQuoteRepository,
    geocoder: FakeGeocoder,
) -> None:
    first = ("user", "Etimesgut, Ankara'da 40 m² güneye bakan eğimli çatı için teklif")
    question_1 = ("assistant", "Müşterinin adı, çatının eğimi ve tüketimi nedir?")
    second = ("user", "Ayşe Yılmaz, 30 derece")
    question_2 = ("assistant", "Aylık tüketimi nedir?")
    third = ("user", "Aylık 500 kWh")
    model = Script(
        asking("customer.name", "roof.tilt_deg", "consumption", question=question_1[1]),
        asking("consumption", question=question_2[1]),
        create(),
        TextReply(REPLY),
    )
    client = client_with(client_factory, model)

    one = ask(client, conversation_of(first)).json()
    two = ask(client, conversation_of(first, question_1, second)).json()
    three = ask(client, conversation_of(first, question_1, second, question_2, third)).json()

    assert (one["quote"], two["quote"]) == (None, None)
    assert (one["reply"], two["reply"]) == (question_1[1], question_2[1])
    assert two["missing_fields"] == ["consumption"]
    assert three["missing_fields"] == []
    (stored,) = quote_repository.stored
    assert three["quote"]["id"] == str(stored.id)
    assert stored.quote.customer.name == "Ayşe Yılmaz"
    assert geocoder.addresses == ["Etimesgut, Ankara"]
    # The last request carried the whole history, the earlier questions included.
    assert [m.content for m in model.calls[2].messages] == [
        first[1],
        question_1[1],
        second[1],
        question_2[1],
        third[1],
    ]


# --- Digits in replies without a Quote -------------------------------------------------------


def test_a_question_echoing_the_sales_reps_figure_passes(client_factory: ClientFactory) -> None:
    question = "40 m² çatının eğimi kaç derece?"
    model = Script(asking("roof.tilt_deg", question=question))
    client = client_with(client_factory, model)

    body = ask(client, conversation("Etimesgut'ta 40 m² güneye bakan çatı için teklif")).json()

    assert body["reply"] == question
    assert len(model.calls) == 1


def test_a_question_inventing_a_figure_is_retried_with_the_violation_as_feedback(
    client_factory: ClientFactory,
) -> None:
    model = Script(
        asking("roof.tilt_deg", question="35 m² çatının eğimi kaç derece?"),
        asking("roof.tilt_deg", question="Çatının eğimi kaç derece?"),
    )
    client = client_with(client_factory, model)

    body = ask(client, conversation("Etimesgut'ta 40 m² çatı için teklif")).json()

    assert body["reply"] == "Çatının eğimi kaç derece?"
    assert body["missing_fields"] == ["roof.tilt_deg"]
    rejection = model.calls[1].exchanges[0].result["error"]
    assert rejection["violations"][0]["kind"] == "digit_not_in_user_messages"
    assert "35" in rejection["violations"][0]["detail"]


def test_a_question_that_keeps_inventing_a_figure_is_replaced_by_the_fixed_template(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    bad = asking("customer.name", "roof.tilt_deg", question="35 m² çatının eğimi kaç derece?")
    model = Script(bad, bad)
    client = client_with(client_factory, model)

    body = ask(client, conversation("Etimesgut'ta 40 m² çatı için teklif")).json()

    assert len(model.calls) == 2
    assert "35" not in body["reply"]
    assert "Müşteri adı" in body["reply"]
    assert "Çatı eğimi" in body["reply"]
    assert "Adres" not in body["reply"]
    assert body["missing_fields"] == ["customer.name", "roof.tilt_deg"]
    assert body["quote"] is None
    assert quote_repository.stored == []


def test_a_plain_text_answer_echoing_the_sales_reps_figure_passes(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script(TextReply("40 m² için hangi ilde?")))

    body = ask(client, conversation("40 m² çatı")).json()

    assert body["reply"] == "40 m² için hangi ilde?"


def test_a_plain_text_answer_inventing_a_figure_is_retried_then_replaced_by_the_restate_reply(
    client_factory: ClientFactory,
) -> None:
    model = Script(TextReply("35 m² mi?"), TextReply("Yine 35 m² mi?"))
    client = client_with(client_factory, model)

    body = ask(client, conversation("40 m² çatı")).json()

    assert len(model.calls) == 2
    retry = model.calls[1].rejected_reply
    assert retry is not None
    assert retry.text == "35 m² mi?"
    assert [v.kind.value for v in retry.violations] == ["digit_not_in_user_messages"]
    assert "35" not in body["reply"]
    assert not any(character.isdigit() for character in body["reply"])
    assert "yeniden" in body["reply"]
    assert body["quote"] is None
    assert body["missing_fields"] == []


def test_figures_in_the_assistants_own_earlier_messages_are_not_the_sales_reps(
    client_factory: ClientFactory,
) -> None:
    model = Script(TextReply("12 m² mi?"), TextReply("12 m² mi?"))
    client = client_with(client_factory, model)
    history = conversation_of(
        ("user", "Çatı var"), ("assistant", "Kaç m²? Örneğin 12 m²"), ("user", "Bilmiyorum")
    )

    body = ask(client, history).json()

    assert "12" not in body["reply"]


# --- Tool errors -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "changes"),
    [
        ("validation-error", {"roof__tilt_deg": 120}),
        ("unsupported-subscriber-group", {"subscriber_group": "commercial"}),
        ("no-viable-system", {"roof__usable_area_m2": 2}),
        ("no-compatible-inverter", {"roof__usable_area_m2": 6}),
    ],
)
def test_each_domain_or_validation_error_goes_back_to_the_model_and_leads_to_a_reply(
    client_factory: ClientFactory,
    quote_repository: FakeQuoteRepository,
    slug: str,
    changes: dict[str, Any],
) -> None:
    explanation = "Bilgileri kontrol edip bir daha yazar mısınız?"
    model = Script(create(**changes), TextReply(explanation))
    client = client_with(client_factory, model)

    body = ask(client).json()

    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}{slug}"
    assert error["detail"]
    assert body == {"reply": explanation, "quote": None, "missing_fields": []}
    assert quote_repository.stored == []


def test_a_validation_tool_error_names_the_fields(client_factory: ClientFactory) -> None:
    model = Script(create(roof__tilt_deg=120), TextReply("Eğimi düzeltir misiniz?"))
    client = client_with(client_factory, model)

    ask(client)

    error = model.calls[1].exchanges[0].result["error"]
    assert [item["field"] for item in error["errors"]] == ["roof.tilt_deg"]


def test_an_address_not_found_tool_error_names_the_address_field(
    client_factory: ClientFactory, geocoder: FakeGeocoder
) -> None:
    geocoder.error = AddressNotFoundError()
    model = Script(create(), TextReply("Adresi bulamadım, açık yazar mısınız?"))
    client = client_with(client_factory, model)

    body = ask(client).json()

    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}address-not-found"
    assert [item["field"] for item in error["errors"]] == ["site.address"]
    assert body["reply"] == "Adresi bulamadım, açık yazar mısınız?"


def test_a_location_the_source_rejects_is_a_tool_error(
    client_factory: ClientFactory, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    specific_yield_provider.error = LocationNotSupportedError("Location over the sea")
    model = Script(create(), TextReply("Konum desteklenmiyor."))
    client = client_with(client_factory, model)

    ask(client)

    assert model.calls[1].exchanges[0].result["error"]["type"] == f"{URN}location-not-supported"


def test_an_unavailable_upstream_service_is_a_tool_error_and_the_reply_is_the_models(
    client_factory: ClientFactory,
    specific_yield_provider: FakeSpecificYieldProvider,
    quote_repository: FakeQuoteRepository,
) -> None:
    specific_yield_provider.error = UpstreamUnavailableError("PVGIS", "the request timed out")
    explanation = "Hizmet geçici olarak kullanılamıyor, biraz sonra tekrar deneyin."
    model = Script(create(), TextReply(explanation))
    client = client_with(client_factory, model)

    response = ask(client)

    assert response.status_code == 200
    assert response.json() == {"reply": explanation, "quote": None, "missing_fields": []}
    error = model.calls[1].exchanges[0].result["error"]
    assert error["type"] == f"{URN}upstream-unavailable"
    assert quote_repository.stored == []


def test_an_explanation_with_an_invented_figure_is_retried_then_replaced_by_the_error_template(
    client_factory: ClientFactory,
) -> None:
    model = Script(
        create(roof__tilt_deg=120),
        TextReply("Eğim 35 olmalı."),
        TextReply("Eğim 35 olmalı."),
    )
    client = client_with(client_factory, model)

    body = ask(client, conversation("Eğim 120 derece, 40 m² çatı")).json()

    assert len(model.calls) == 3
    assert "35" not in body["reply"]
    assert "Teklif oluşturulamadı" in body["reply"]
    assert "geçersiz değer" in body["reply"]
    assert body["quote"] is None


def test_the_error_template_names_the_problem_in_turkish(
    client_factory: ClientFactory, geocoder: FakeGeocoder
) -> None:
    geocoder.error = AddressNotFoundError()
    model = Script(create(), TextReply("1 2 3"), TextReply("1 2 3"))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert "Teklif oluşturulamadı" in body["reply"]
    assert "adres bulunamadı" in body["reply"]


# --- The limit without a Quote ---------------------------------------------------------------


def test_tool_errors_count_towards_the_three_call_limit_and_end_in_the_restate_reply(
    client_factory: ClientFactory, quote_repository: FakeQuoteRepository
) -> None:
    bad = create(roof__tilt_deg=120)
    model = Script(bad, bad, bad, TextReply("hiç okunmaz"))
    client = client_with(client_factory, model)

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert len(model.calls) == 3
    assert body["quote"] is None
    assert body["missing_fields"] == []
    assert "yeniden" in body["reply"]
    assert quote_repository.stored == []


def test_the_time_budget_without_a_quote_is_a_200_with_the_restate_reply(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script(5.0), assistant_budget_seconds=0.2)

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["quote"] is None
    assert "yeniden" in body["reply"]


def test_the_time_budget_covers_the_tools_too(
    client_factory: ClientFactory, geocoder: FakeGeocoder, quote_repository: FakeQuoteRepository
) -> None:
    geocoder.delay_seconds = 5.0
    model = Script(create(), TextReply(REPLY))
    client = client_with(client_factory, model, assistant_budget_seconds=0.3)

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["quote"] is None
    assert body["missing_fields"] == []
    assert "yeniden" in body["reply"]
    assert len(model.calls) == 1
    assert quote_repository.stored == []


def test_a_model_failure_before_any_quote_is_still_unavailable(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script(ConversationUnavailableError("HTTP 500")))

    assert ask(client).status_code == 503


def test_an_unknown_tool_is_a_tool_error_the_model_can_correct(
    client_factory: ClientFactory,
) -> None:
    model = Script(ToolCall("send_email", {}), TextReply("Hangi ilde?"))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert model.calls[1].exchanges[0].result["error"]["type"] == f"{URN}unknown-tool"
    assert body["reply"] == "Hangi ilde?"


def test_the_response_schema_lists_the_missing_field_values(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script())

    schema = client.get("/openapi.json").json()["components"]["schemas"]

    items = schema["AssistantResponse"]["properties"]["missing_fields"]["items"]
    assert items == {"$ref": "#/components/schemas/MissingField"}
    assert schema["MissingField"]["enum"] == ALL_FIELDS


def test_a_question_that_holds_a_placeholder_is_refused_like_any_other_reply(
    client_factory: ClientFactory,
) -> None:
    model = Script(
        asking("roof.tilt_deg", question="Sayın {customer_name}, eğim nedir?"),
        asking("roof.tilt_deg", question="Eğim nedir?"),
    )
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert body["reply"] == "Eğim nedir?"
    kinds = [v["kind"] for v in model.calls[1].exchanges[0].result["error"]["violations"]]
    assert kinds == ["unavailable_placeholder"]


def test_a_plain_text_with_braces_is_retried_then_replaced_by_the_restate_reply(
    client_factory: ClientFactory,
) -> None:
    model = Script(TextReply("Merhaba {customer_name}"), TextReply("Merhaba {customer_name}"))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert len(model.calls) == 2
    assert "{" not in body["reply"]
    assert "yeniden" in body["reply"]


def test_a_refused_question_does_not_use_up_the_retry_of_the_text_that_follows(
    client_factory: ClientFactory,
) -> None:
    model = Script(
        asking("roof.tilt_deg", question="35 derece mi?"),
        TextReply("35 m² mi?"),
        TextReply("Kaç metrekare?"),
    )
    client = client_with(client_factory, model)

    body = ask(client, conversation("Etimesgut'ta 40 m² çatı için teklif")).json()

    assert body["reply"] == "Kaç metrekare?"
    assert len(model.calls) == 3


def test_a_superscript_in_the_reply_after_a_quote_is_not_a_stray_digit(
    client_factory: ClientFactory,
) -> None:
    reply = "Çatı alanı m² olarak alındı; teklif numarası {quote_number}."
    model = Script(create(), TextReply(reply))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert len(model.calls) == 2
    assert body["reply"] == reply.replace("{quote_number}", body["quote"]["quote_number"])


def test_an_empty_text_reply_is_retried_and_then_replaced(client_factory: ClientFactory) -> None:
    model = Script(TextReply("  "), TextReply(""))
    client = client_with(client_factory, model)

    body = ask(client).json()

    assert len(model.calls) == 2
    assert "yeniden" in body["reply"]


def test_the_missing_fields_are_documented_as_a_list_of_field_paths(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, Script())

    schema = client.get("/openapi.json").json()

    description = schema["components"]["schemas"]["AssistantResponse"]["properties"][
        "missing_fields"
    ]["description"]
    assert "Always empty" not in description
    assert "customer.name" in description
