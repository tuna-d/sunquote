"""The quote assistant's conversation policy: one request, at most `MAX_MODEL_CALLS` model calls.

The model either calls a tool or answers with text. A tool call is run through the tools and its
result goes back to the model. This module decides what each turn ends in and which replies are
acceptable; it produces no text. The caller turns the `AssistantOutcome` into Turkish text from
fixed templates and fills the Quote's figures into the model's own text (ADR 0001).

A turn ends in one of these:

- A Quote exists: the model's text is the reply (`QUOTE_REPLY`). It may refer to figures only
  through the Quote's placeholders (ADR 0001). A text that breaks the rules is sent back once;
  when it breaks them again, or the model, the call limit or the caller's time budget fails, the
  fixed `CONFIRMATION` is the reply.
- The model asked for missing fields: its question is the reply (`QUESTION`), or the fixed
  question for those fields (`FIXED_QUESTION`) when its own was refused twice.
- No Quote and no question: the model's text is the reply (`TEXT`). A text refused twice gives
  `ERROR_EXPLANATION` when the last tool call failed, otherwise `RESTATE`. `RESTATE` also ends a
  turn that ran out of calls or time without a Quote.

A reply without a Quote has no placeholders to fill, so it may hold none of the placeholder
syntax, and its digits may only echo what the Sales Rep wrote (`validate_echoed_digits`). The
reply's rules are checked here, so the retry rule is also here: each kind of reply (a question or
a text) gets one retry per request, and a refusal of one kind does not use up the other's.

The time budget is the caller's: it stops `run` when time is up and asks `out_of_time` for the
outcome. The domain reads no clock. An `Assistant` serves one request.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from sunquote.domain.conversation import (
    MAX_MODEL_CALLS,
    REPLY_MAX_CHARACTERS,
    ChatMessage,
    MissingField,
    ReplyRejection,
    TextReply,
    ToolCall,
    ToolDeclaration,
    ToolExchange,
    validate_echoed_digits,
)
from sunquote.domain.errors import ConversationUnavailableError, GeminiBudgetExhaustedError
from sunquote.domain.narrative import (
    Violation,
    ViolationKind,
    validate_placeholder_syntax,
    validate_text,
)
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.ports import ConversationModel, StoredQuote

logger = logging.getLogger(__name__)

REPLY_FIELD = "reply"


class OutcomeKind(StrEnum):
    """What a turn ends in. The caller picks the text for each."""

    QUOTE_REPLY = "quote_reply"
    CONFIRMATION = "confirmation"
    QUESTION = "question"
    FIXED_QUESTION = "fixed_question"
    TEXT = "text"
    ERROR_EXPLANATION = "error_explanation"
    RESTATE = "restate"


@dataclass(frozen=True, slots=True)
class AssistantOutcome:
    """How a turn ended. `text` is the model's own text for `QUOTE_REPLY`, `QUESTION` and
    `TEXT`, and None otherwise. `quote` is the Quote created in this request, if any.
    `missing_fields` are the fields a question asks for. `problem` is the problem type of the
    last tool call for `ERROR_EXPLANATION`."""

    kind: OutcomeKind
    text: str | None = None
    quote: StoredQuote | None = None
    missing_fields: tuple[MissingField, ...] = ()
    problem: str | None = None


@dataclass(frozen=True, slots=True)
class AskedQuestion:
    """The model asked the Sales Rep for the `fields` in `text`."""

    fields: tuple[MissingField, ...]
    text: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What running a tool did.

    `content` is what the model is told. `problem` is the type of the failure when the call
    failed. `created` is the Quote the call created, `asked` the question it asked.
    """

    content: Mapping[str, Any]
    problem: str | None = None
    created: StoredQuote | None = None
    asked: AskedQuestion | None = None


class AssistantTools(Protocol):
    """The tools the model may call. A failure is a result with a `problem`, never an
    exception, so the model can correct itself."""

    @property
    def declarations(self) -> Sequence[ToolDeclaration]:
        """The tools as the model sees them."""
        ...

    async def run(self, call: ToolCall) -> ToolResult:
        """Run the tool `call` names with its arguments."""
        ...

    def rejection(self, violations: Sequence[Violation]) -> ToolResult:
        """The result for a call whose question the assistant refused, with the violations."""
        ...


def _empty_reply(field: str) -> Violation:
    return Violation(ViolationKind.MISSING_FIELD, field, "the reply is empty; write it")


def validate_reply_without_quote(
    text: str, *, field: str, messages: Sequence[ChatMessage]
) -> tuple[Violation, ...]:
    """The rules for a reply when no Quote exists (a question, the explanation of an error,
    plain text): not empty, no placeholder syntax, and digits only as the Sales Rep wrote them."""
    if not text.strip():
        return (_empty_reply(field),)
    return (
        *validate_placeholder_syntax(text, field=field, available_placeholders=()),
        *validate_echoed_digits(text, field=field, messages=messages),
    )


def validate_reply_after_quote(
    text: str, *, field: str, quote: StoredQuote
) -> tuple[Violation, ...]:
    """The rules for a reply after a Quote was created (ADR 0001): not empty, and figures only
    through the Quote's own placeholders."""
    if not text.strip():
        return (_empty_reply(field),)
    return validate_text(
        text,
        field=field,
        available_placeholders=build_narrative_context(quote.quote).available_placeholders,
        max_length=REPLY_MAX_CHARACTERS,
    )


class _ReplyKind(StrEnum):
    QUESTION = "question"
    TEXT = "text"


class Assistant:
    """Runs the loop for one request with a model and its tools."""

    def __init__(self, *, model: ConversationModel, tools: AssistantTools) -> None:
        self._model = model
        self._tools = tools
        self._created: StoredQuote | None = None
        self._last_problem: str | None = None

    async def run(self, messages: Sequence[ChatMessage]) -> AssistantOutcome:
        """Raises `ConversationUnavailableError` when the model fails and no Quote exists, and
        `GeminiBudgetExhaustedError` when the day's budget is spent and no Quote exists. A
        turn that runs out of calls without a Quote is `RESTATE`, not an error."""
        exchanges: list[ToolExchange] = []
        rejection: ReplyRejection | None = None
        retried: set[_ReplyKind] = set()

        for _ in range(MAX_MODEL_CALLS):
            try:
                reply = await self._model.respond(
                    messages=messages,
                    tools=self._tools.declarations,
                    exchanges=tuple(exchanges),
                    rejected_reply=rejection,
                )
            except (ConversationUnavailableError, GeminiBudgetExhaustedError) as error:
                if self._created is None:
                    raise
                logger.warning("Conversation model failed after a Quote: %s", error)
                return self._confirmation(self._created)

            rejection = None
            if isinstance(reply, TextReply):
                violations = self._validate(reply.text, messages)
                if not violations:
                    return self._text_outcome(reply.text)
                logger.info("Assistant reply rejected: %s", [v.kind.value for v in violations])
                if _ReplyKind.TEXT in retried:
                    return self._refused_text_outcome()
                retried.add(_ReplyKind.TEXT)
                rejection = ReplyRejection(reply.text, violations)
                continue

            result = await self._run_tool(reply)
            exchanges.append(ToolExchange(reply, result.content))
            if result.asked is None:
                continue
            violations = self._validate(result.asked.text, messages)
            if not violations:
                return AssistantOutcome(
                    OutcomeKind.QUESTION, result.asked.text, missing_fields=result.asked.fields
                )
            logger.info("Assistant question rejected: %s", [v.kind.value for v in violations])
            if _ReplyKind.QUESTION in retried:
                return AssistantOutcome(
                    OutcomeKind.FIXED_QUESTION, missing_fields=result.asked.fields
                )
            retried.add(_ReplyKind.QUESTION)
            refusal = self._tools.rejection(violations)
            self._last_problem = refusal.problem
            exchanges[-1] = ToolExchange(reply, refusal.content)

        return self.out_of_time()

    def out_of_time(self) -> AssistantOutcome:
        """The outcome when the run ended without a reply (the caller's time budget ran out or
        the call limit was reached): the confirmation when a Quote exists, else `RESTATE`."""
        if self._created is not None:
            return self._confirmation(self._created)
        return AssistantOutcome(OutcomeKind.RESTATE)

    async def _run_tool(self, call: ToolCall) -> ToolResult:
        result = await self._tools.run(call)
        if result.created is not None:
            self._created = result.created
        self._last_problem = result.problem
        return result

    def _validate(self, text: str, messages: Sequence[ChatMessage]) -> tuple[Violation, ...]:
        if self._created is None:
            return validate_reply_without_quote(text, field=REPLY_FIELD, messages=messages)
        return validate_reply_after_quote(text, field=REPLY_FIELD, quote=self._created)

    def _text_outcome(self, text: str) -> AssistantOutcome:
        if self._created is None:
            return AssistantOutcome(OutcomeKind.TEXT, text)
        return AssistantOutcome(OutcomeKind.QUOTE_REPLY, text, quote=self._created)

    def _refused_text_outcome(self) -> AssistantOutcome:
        if self._created is not None:
            return self._confirmation(self._created)
        if self._last_problem is not None:
            return AssistantOutcome(OutcomeKind.ERROR_EXPLANATION, problem=self._last_problem)
        return AssistantOutcome(OutcomeKind.RESTATE)

    @staticmethod
    def _confirmation(stored: StoredQuote) -> AssistantOutcome:
        return AssistantOutcome(OutcomeKind.CONFIRMATION, quote=stored)
