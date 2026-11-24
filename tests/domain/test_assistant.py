"""The assistant's conversation policy with scripted tools and a scripted model: how many
calls, which replies are accepted, how often a refused reply is retried and what a turn ends
in. No HTTP and no Quote creation: the tools are fakes."""

import asyncio
from collections.abc import Sequence
from uuid import UUID

import pytest

from sunquote.domain.assistant import (
    AskedQuestion,
    Assistant,
    AssistantOutcome,
    OutcomeKind,
    ToolResult,
)
from sunquote.domain.conversation import (
    ASK_FOR_MISSING_FIELDS,
    CREATE_QUOTE,
    MAX_MODEL_CALLS,
    ChatMessage,
    MessageRole,
    MissingField,
    TextReply,
    ToolCall,
    ToolDeclaration,
)
from sunquote.domain.errors import ConversationUnavailableError
from sunquote.domain.narrative import Violation, ViolationKind
from sunquote.domain.ports import StoredQuote
from tests.eval.scenarios import SCENARIOS
from tests.fakes import NARRATIVE_TIME
from tests.fakes import ScriptedConversationModel as Script

STORED = StoredQuote(UUID(int=1), NARRATIVE_TIME, SCENARIOS[0].build())
FAILED = "urn:test:problem:failed"
REJECTED = "urn:test:problem:rejected"
USER_SAYS = [ChatMessage(MessageRole.USER, "Etimesgut'ta 40 m² çatı")]
CREATE = ToolCall(CREATE_QUOTE, {})
ASK = ToolCall(ASK_FOR_MISSING_FIELDS, {})


def created() -> ToolResult:
    return ToolResult({"status": "created"}, created=STORED)


def failed() -> ToolResult:
    return ToolResult({"error": {"type": FAILED}}, problem=FAILED)


def asked(text: str, *fields: MissingField) -> ToolResult:
    return ToolResult(
        {"status": "asked"}, asked=AskedQuestion(fields or (MissingField.ROOF_TILT,), text)
    )


class ScriptedTools:
    """Answers each tool call with the next scripted result; refusals get `REJECTED`."""

    declarations = (ToolDeclaration(CREATE_QUOTE, "creates", {}),)

    def __init__(self, *results: ToolResult) -> None:
        self._results = list(results)
        self.calls: list[ToolCall] = []
        self.refusals: list[Sequence[Violation]] = []

    async def run(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return self._results.pop(0)

    def rejection(self, violations: Sequence[Violation]) -> ToolResult:
        self.refusals.append(violations)
        return ToolResult({"error": {"type": REJECTED}}, problem=REJECTED)


async def run(
    model: Script, tools: ScriptedTools, messages: Sequence[ChatMessage] = USER_SAYS
) -> AssistantOutcome:
    return await Assistant(model=model, tools=tools).run(messages)


def kinds(violations: Sequence[Violation]) -> list[ViolationKind]:
    return [violation.kind for violation in violations]


# --- A Quote exists --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_valid_text_after_a_quote_is_the_quote_reply() -> None:
    model = Script(CREATE, TextReply("{quote_number} hazır."))

    outcome = await run(model, ScriptedTools(created()))

    assert (outcome.kind, outcome.text, outcome.quote) == (
        OutcomeKind.QUOTE_REPLY,
        "{quote_number} hazır.",
        STORED,
    )


@pytest.mark.anyio
async def test_a_superscript_after_a_quote_is_not_a_stray_digit() -> None:
    model = Script(CREATE, TextReply("Çatı m² olarak alındı."))

    outcome = await run(model, ScriptedTools(created()))

    assert outcome.kind is OutcomeKind.QUOTE_REPLY
    assert len(model.calls) == 2


@pytest.mark.anyio
async def test_a_stray_figure_after_a_quote_is_retried_once_then_confirmed() -> None:
    model = Script(CREATE, TextReply("8,4 kWp"), TextReply("8,4 kWp"))

    outcome = await run(model, ScriptedTools(created()))

    assert (outcome.kind, outcome.quote) == (OutcomeKind.CONFIRMATION, STORED)
    retry = model.calls[2].rejected_reply
    assert retry is not None
    assert kinds(retry.violations) == [ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER]


@pytest.mark.anyio
async def test_a_model_failure_after_a_quote_is_the_confirmation() -> None:
    model = Script(CREATE, ConversationUnavailableError("HTTP 500"))

    outcome = await run(model, ScriptedTools(created()))

    assert (outcome.kind, outcome.quote) == (OutcomeKind.CONFIRMATION, STORED)


@pytest.mark.anyio
async def test_a_model_failure_without_a_quote_is_raised() -> None:
    model = Script(ConversationUnavailableError("HTTP 500"))

    with pytest.raises(ConversationUnavailableError):
        await run(model, ScriptedTools())


# --- No Quote: plain text --------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_text_that_echoes_the_sales_reps_figures_is_the_reply() -> None:
    model = Script(TextReply("40 m² için hangi ilde?"))

    outcome = await run(model, ScriptedTools())

    assert (outcome.kind, outcome.text, outcome.quote) == (
        OutcomeKind.TEXT,
        "40 m² için hangi ilde?",
        None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["Merhaba {customer_name}", "Eksik {", "{nothing_here} var"])
async def test_a_text_without_a_quote_may_not_hold_placeholder_syntax(text: str) -> None:
    model = Script(TextReply(text), TextReply(text))

    outcome = await run(model, ScriptedTools())

    assert outcome.kind is OutcomeKind.RESTATE
    retry = model.calls[1].rejected_reply
    assert retry is not None
    assert retry.text == text
    assert retry.violations
    assert set(kinds(retry.violations)) <= {
        ViolationKind.UNKNOWN_PLACEHOLDER,
        ViolationKind.UNAVAILABLE_PLACEHOLDER,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("blank", ["", "   \n"])
async def test_an_empty_text_is_a_violation_and_gets_one_retry(blank: str) -> None:
    model = Script(TextReply(blank), TextReply("Hangi ilde?"))

    outcome = await run(model, ScriptedTools())

    assert (outcome.kind, outcome.text) == (OutcomeKind.TEXT, "Hangi ilde?")
    retry = model.calls[1].rejected_reply
    assert retry is not None
    assert kinds(retry.violations) == [ViolationKind.MISSING_FIELD]


@pytest.mark.anyio
async def test_an_empty_text_that_stays_empty_falls_back() -> None:
    model = Script(TextReply(""), TextReply(" "))

    outcome = await run(model, ScriptedTools())

    assert outcome.kind is OutcomeKind.RESTATE


@pytest.mark.anyio
async def test_an_empty_text_after_a_quote_falls_back_to_the_confirmation() -> None:
    model = Script(CREATE, TextReply(""), TextReply(""))

    outcome = await run(model, ScriptedTools(created()))

    assert outcome.kind is OutcomeKind.CONFIRMATION


@pytest.mark.anyio
async def test_a_refused_text_after_a_failed_tool_call_names_the_problem() -> None:
    model = Script(CREATE, TextReply("35 olmalı"), TextReply("35 olmalı"))

    outcome = await run(model, ScriptedTools(failed()))

    assert (outcome.kind, outcome.problem, outcome.quote) == (
        OutcomeKind.ERROR_EXPLANATION,
        FAILED,
        None,
    )


@pytest.mark.anyio
async def test_a_refused_text_with_no_tool_call_asks_to_restate() -> None:
    model = Script(TextReply("35 olmalı"), TextReply("35 olmalı"))

    outcome = await run(model, ScriptedTools())

    assert (outcome.kind, outcome.problem) == (OutcomeKind.RESTATE, None)


# --- No Quote: questions ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_question_is_the_reply_with_its_fields() -> None:
    model = Script(ASK)
    tools = ScriptedTools(asked("Eğim kaç derece?", MissingField.ROOF_TILT))

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.text, outcome.missing_fields) == (
        OutcomeKind.QUESTION,
        "Eğim kaç derece?",
        (MissingField.ROOF_TILT,),
    )
    assert len(model.calls) == 1


@pytest.mark.anyio
async def test_a_question_with_an_invented_figure_goes_back_as_the_tools_rejection() -> None:
    model = Script(ASK, ASK)
    tools = ScriptedTools(asked("35 derece mi?"), asked("Eğim kaç derece?"))

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.text) == (OutcomeKind.QUESTION, "Eğim kaç derece?")
    (refusal,) = tools.refusals
    assert kinds(refusal) == [ViolationKind.DIGIT_NOT_IN_USER_MESSAGES]
    (exchange,) = model.calls[1].exchanges
    assert exchange.result == {"error": {"type": REJECTED}}


@pytest.mark.anyio
async def test_a_question_that_keeps_breaking_the_rule_becomes_the_fixed_question() -> None:
    model = Script(ASK, ASK)
    fields = (MissingField.ROOF_TILT, MissingField.CONSUMPTION)
    tools = ScriptedTools(asked("35 derece mi?", *fields), asked("35 derece mi?", *fields))

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.text, outcome.missing_fields) == (
        OutcomeKind.FIXED_QUESTION,
        None,
        fields,
    )


@pytest.mark.anyio
async def test_a_question_may_not_hold_placeholder_syntax() -> None:
    model = Script(ASK, ASK)
    tools = ScriptedTools(asked("Sayın {customer_name}, eğim?"), asked("Eğim kaç derece?"))

    outcome = await run(model, tools)

    assert outcome.text == "Eğim kaç derece?"
    (refusal,) = tools.refusals
    assert kinds(refusal) == [ViolationKind.UNAVAILABLE_PLACEHOLDER]


# --- One retry per reply kind ----------------------------------------------------------------


@pytest.mark.anyio
async def test_a_refused_question_does_not_use_up_the_retry_of_a_later_text() -> None:
    model = Script(ASK, TextReply("35 m² mi?"), TextReply("Kaç metrekare?"))
    tools = ScriptedTools(asked("35 derece mi?"))

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.text) == (OutcomeKind.TEXT, "Kaç metrekare?")
    retry = model.calls[2].rejected_reply
    assert retry is not None
    assert retry.text == "35 m² mi?"


@pytest.mark.anyio
async def test_a_refused_text_does_not_use_up_the_retry_of_a_later_question() -> None:
    model = Script(TextReply("35 m² mi?"), ASK, ASK)
    tools = ScriptedTools(asked("35 derece mi?"), asked("Eğim kaç derece?"))

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.text) == (OutcomeKind.QUESTION, "Eğim kaç derece?")
    assert len(tools.refusals) == 1


# --- The limits ------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_model_is_called_at_most_three_times() -> None:
    assert MAX_MODEL_CALLS == 3
    model = Script(CREATE, CREATE, CREATE, TextReply("hiç okunmaz"))
    tools = ScriptedTools(failed(), failed(), failed())

    outcome = await run(model, tools)

    assert len(model.calls) == 3
    assert outcome.kind is OutcomeKind.RESTATE


@pytest.mark.anyio
async def test_the_call_limit_after_a_quote_is_the_confirmation() -> None:
    model = Script(CREATE, CREATE, CREATE)
    tools = ScriptedTools(created(), failed(), failed())

    outcome = await run(model, tools)

    assert (outcome.kind, outcome.quote) == (OutcomeKind.CONFIRMATION, STORED)


@pytest.mark.anyio
async def test_a_run_the_caller_stops_gives_the_outcome_of_what_happened_so_far() -> None:
    assistant = Assistant(model=Script(CREATE, 5.0), tools=ScriptedTools(created()))

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(assistant.run(USER_SAYS), timeout=0.2)

    outcome = assistant.out_of_time()
    assert (outcome.kind, outcome.quote) == (OutcomeKind.CONFIRMATION, STORED)


def test_a_run_stopped_before_any_quote_asks_to_restate() -> None:
    assistant = Assistant(model=Script(), tools=ScriptedTools())

    assert assistant.out_of_time().kind is OutcomeKind.RESTATE
