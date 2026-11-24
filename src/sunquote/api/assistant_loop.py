"""The quote assistant's tool loop: one request, at most `MAX_MODEL_CALLS` model calls.

The model either calls a tool or answers with text. A tool call is run through the tool
registry and its result goes back to the model. The turn ends in one of three ways:

- A Quote exists: the model's text is the reply. It is checked against the Quote's available
  placeholders (ADR 0001), asked once more when it breaks the rules, and replaced by a fixed
  Turkish confirmation when it still does or when the model, the call limit or the time budget
  fails.
- The model asked for missing fields (`ask_for_missing_fields`): its question is the reply.
- No Quote and no question: the model's text is the reply. It may hold digits only as the Sales
  Rep wrote them. A violation gets one retry and then a fixed Turkish reply: the error
  explanation when the last tool call failed, otherwise a request to restate the information.
  The same request-to-restate reply ends a turn that ran out of calls or time without a Quote.

The loop keeps no state between requests.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sunquote.api.assistant_text import (
    RESTATE_REPLY,
    SYSTEM_INSTRUCTION,
    fixed_confirmation,
    fixed_error_explanation,
    fixed_question,
)
from sunquote.api.assistant_tools import AssistantTool, ConversationState, tool_error
from sunquote.api.errors import ProblemType
from sunquote.api.narrative_text import placeholder_figures
from sunquote.api.option_views import option_views
from sunquote.domain.conversation import (
    MAX_MODEL_CALLS,
    REPLY_MAX_CHARACTERS,
    ChatMessage,
    ReplyRejection,
    TextReply,
    ToolCall,
    ToolExchange,
    validate_echoed_digits,
)
from sunquote.domain.errors import ConversationUnavailableError
from sunquote.domain.narrative import Violation, validate_text
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.placeholders import fill_placeholders
from sunquote.domain.ports import ConversationModel, StoredQuote

logger = logging.getLogger(__name__)

REPLY_FIELD = "reply"
UNKNOWN_TOOL = ProblemType("unknown-tool", "Unknown tool", 422)


@dataclass(frozen=True, slots=True)
class AssistantOutcome:
    """The reply for the Sales Rep, the Quote created in this request, if any, and the fields
    the reply asks for (field paths), if it is a question."""

    reply: str
    quote: StoredQuote | None
    missing_fields: tuple[str, ...] = ()


class Assistant:
    """Runs the loop for one request with a model and a registry of tools.

    `document_url` turns a stored Quote's id into the link to its document, which the fixed
    confirmation shows. `budget_seconds` is the total time for the model calls and the tools.
    """

    def __init__(
        self,
        *,
        model: ConversationModel,
        tools: Sequence[AssistantTool],
        document_url: Callable[[UUID], str],
        budget_seconds: float,
    ) -> None:
        self._model = model
        self._tools = {tool.declaration.name: tool for tool in tools}
        self._declarations = tuple(tool.declaration for tool in tools)
        self._document_url = document_url
        self._budget_seconds = budget_seconds

    async def run(self, messages: Sequence[ChatMessage]) -> AssistantOutcome:
        """Raises `ConversationUnavailableError` when the model fails and no Quote exists. A
        turn that runs out of calls or time without a Quote is a reply, not an error."""
        state = ConversationState(messages=messages)
        exchanges: list[ToolExchange] = []
        rejection: ReplyRejection | None = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._budget_seconds

        for _ in range(MAX_MODEL_CALLS):
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                async with asyncio.timeout(remaining):
                    reply = await self._model.respond(
                        system_instruction=SYSTEM_INSTRUCTION,
                        messages=messages,
                        tools=self._declarations,
                        exchanges=tuple(exchanges),
                        rejected_reply=rejection,
                    )
            except TimeoutError:
                break
            except ConversationUnavailableError as error:
                if state.created is None:
                    raise
                logger.warning("Conversation model failed after a Quote: %s", error.reason)
                return self._confirmed(state.created)

            rejection = None
            if isinstance(reply, ToolCall):
                exchanges.append(ToolExchange(reply, await self._run_tool(reply, state)))
                if state.question is not None:
                    return self._asked(state)
                continue
            violations = self._violations(reply, state, messages)
            if not violations:
                if state.created is None:
                    return AssistantOutcome(reply.text, None)
                return AssistantOutcome(self._fill(reply, state.created), state.created)
            logger.info("Assistant reply rejected: %s", [v.kind.value for v in violations])
            if state.reply_retried:
                if state.created is not None:
                    return self._confirmed(state.created)
                return AssistantOutcome(self._after_refusal(exchanges), None)
            state.reply_retried = True
            rejection = ReplyRejection(reply.text, violations)

        if state.created is not None:
            return self._confirmed(state.created)
        return AssistantOutcome(RESTATE_REPLY, None)

    async def _run_tool(self, call: ToolCall, state: ConversationState) -> Mapping[str, Any]:
        tool = self._tools.get(call.name)
        if tool is None:
            return tool_error(UNKNOWN_TOOL, f"There is no tool named {call.name!r}.")
        return await tool.handler(call.arguments, state)

    def _violations(
        self, reply: TextReply, state: ConversationState, messages: Sequence[ChatMessage]
    ) -> tuple[Violation, ...]:
        if state.created is None:
            return validate_echoed_digits(reply.text, field=REPLY_FIELD, messages=messages)
        context = build_narrative_context(state.created.quote)
        return validate_text(
            reply.text,
            field=REPLY_FIELD,
            available_placeholders=context.available_placeholders,
            max_length=REPLY_MAX_CHARACTERS,
        )

    def _fill(self, reply: TextReply, stored: StoredQuote) -> str:
        return fill_placeholders(reply.text, placeholder_figures(stored, option_views(stored)))

    def _confirmed(self, stored: StoredQuote) -> AssistantOutcome:
        return AssistantOutcome(fixed_confirmation(stored, self._document_url(stored.id)), stored)

    def _asked(self, state: ConversationState) -> AssistantOutcome:
        question = state.question
        assert question is not None
        text = question.text if question.text is not None else fixed_question(question.fields)
        return AssistantOutcome(text, None, tuple(field.value for field in question.fields))

    def _after_refusal(self, exchanges: Sequence[ToolExchange]) -> str:
        """The fixed reply for a text the assistant refused twice when no Quote exists: the
        error explanation when the last tool call failed with a problem the template can name,
        otherwise the request to restate the information."""
        if exchanges:
            error = exchanges[-1].result.get("error")
            if isinstance(error, Mapping):
                return fixed_error_explanation(str(error.get("type"))) or RESTATE_REPLY
        return RESTATE_REPLY
