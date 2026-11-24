import pytest

from sunquote.domain.conversation import ChatMessage, MessageRole, MissingField, TextReply, ToolCall
from sunquote.domain.errors import ConversationUnavailableError
from tests.eval.extraction import ExtractionScenario
from tests.eval.extraction_runner import MODEL_RETRIES, PacedRetryModel, evaluate_extraction
from tests.fakes import ScriptedConversationModel

ARGUMENTS = {
    "customer": {"name": "Ada Örnek"},
    "site": {"address": "Ankara"},
    "roof": {"roof_type": "flat", "usable_area_m2": 40},
    "consumption": {"monthly_consumption_kwh": 300},
    "subscriber_group": "residential",
}


@pytest.mark.anyio
async def test_follow_up_resends_the_conversation_and_grades_the_final_call() -> None:
    question = "Müşterinin adı nedir?"
    model = ScriptedConversationModel(
        ToolCall("ask_for_missing_fields", {"fields": ["customer.name"], "question": question}),
        ToolCall("create_quote", ARGUMENTS),
        TextReply("Teklifiniz hazır."),
    )
    scenario = ExtractionScenario(
        name="follow-up",
        messages=["Ankara'da düz çatı, aylık 300 kWh.", "Ada Örnek."],
        arguments=ARGUMENTS,
    )

    grades = await evaluate_extraction(scenario, model=model, budget_seconds=1)

    assert all(grades.values())
    assert [message.role for message in model.calls[1].messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert model.calls[1].messages[1].content == question


@pytest.mark.anyio
async def test_question_fails_after_an_invalid_create_attempt() -> None:
    model = ScriptedConversationModel(
        ToolCall("create_quote", {}),
        ToolCall("ask_for_missing_fields", {"fields": ["customer.name"], "question": "Adı nedir?"}),
    )
    scenario = ExtractionScenario(
        name="question",
        messages=["İsmi henüz bilmiyorum."],
        missing_fields=[MissingField.CUSTOMER_NAME],
    )

    assert await evaluate_extraction(scenario, model=model, budget_seconds=1) == {
        "create_quote": False,
        "missing_fields": True,
    }


@pytest.mark.anyio
async def test_a_rate_limited_call_is_repeated_after_the_pacing_delay() -> None:
    scripted = ScriptedConversationModel(
        ConversationUnavailableError("HTTP 429"),
        ConversationUnavailableError("HTTP 429"),
        TextReply("Hangi ilde?"),
    )
    scenario = ExtractionScenario(
        name="rate-limited",
        messages=["İsmi henüz bilmiyorum."],
        missing_fields=[MissingField.CUSTOMER_NAME],
    )
    model = PacedRetryModel(scripted, delay_seconds=0)

    reply = await model.respond(
        messages=[ChatMessage(MessageRole.USER, scenario.messages[0])], tools=()
    )

    assert reply == TextReply("Hangi ilde?")
    assert len(scripted.calls) == 3


@pytest.mark.anyio
async def test_a_call_that_keeps_failing_is_raised_after_the_retries() -> None:
    failures = [ConversationUnavailableError("HTTP 429") for _ in range(MODEL_RETRIES + 1)]
    scripted = ScriptedConversationModel(*failures)
    model = PacedRetryModel(scripted, delay_seconds=0)

    with pytest.raises(ConversationUnavailableError):
        await model.respond(messages=[ChatMessage(MessageRole.USER, "merhaba")], tools=())

    assert len(scripted.calls) == MODEL_RETRIES + 1


@pytest.mark.anyio
async def test_a_scenario_survives_one_rate_limit() -> None:
    model = PacedRetryModel(
        ScriptedConversationModel(
            ConversationUnavailableError("HTTP 429"),
            ToolCall(
                "ask_for_missing_fields",
                {"fields": ["customer.name"], "question": "Adı nedir?"},
            ),
        ),
        delay_seconds=0,
    )
    scenario = ExtractionScenario(
        name="question",
        messages=["İsmi henüz bilmiyorum."],
        missing_fields=[MissingField.CUSTOMER_NAME],
    )

    grades = await evaluate_extraction(scenario, model=model, budget_seconds=1)

    assert all(grades.values())
