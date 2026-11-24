import pytest

from sunquote.api.assistant_tools import MissingField
from sunquote.domain.conversation import MessageRole, TextReply, ToolCall
from tests.eval.extraction import ExtractionScenario
from tests.eval.extraction_runner import evaluate_extraction
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
