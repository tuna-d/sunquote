"""The quote assistant's tool loop: one request, at most `MAX_MODEL_CALLS` model calls.

The model either calls a tool or answers with text. A tool call is run through the tool
registry and its result goes back to the model. Once a Quote exists, the model's text is the
reply to the Sales Rep: it is checked against the Quote's available placeholders (ADR 0001),
asked once more when it breaks the rules, and replaced by a fixed Turkish confirmation when it
still does or when the model, the call limit or the time budget fails. The loop keeps no state
between requests.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sunquote.api.assistant_text import SYSTEM_INSTRUCTION, fixed_confirmation
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
    """The reply for the Sales Rep, and the Quote created in this request, if any."""

    reply: str
    quote: StoredQuote | None


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
        """Raises `ConversationUnavailableError` when no Quote exists and the model fails or
        does not finish within the call limit and the time budget."""
        state = ConversationState()
        exchanges: list[ToolExchange] = []
        rejection: ReplyRejection | None = None
        retried = False
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

            if isinstance(reply, ToolCall):
                exchanges.append(ToolExchange(reply, await self._run_tool(reply, state)))
                rejection = None
            elif state.created is None:
                return AssistantOutcome(reply.text, None)
            else:
                violations = self._violations(reply, state.created)
                if not violations:
                    return AssistantOutcome(self._fill(reply, state.created), state.created)
                logger.info("Assistant reply rejected: %s", [v.kind.value for v in violations])
                if retried:
                    break
                retried = True
                rejection = ReplyRejection(reply.text, violations)

        if state.created is None:
            raise ConversationUnavailableError(
                "the model gave no answer within the call limit and the time budget"
            )
        return self._confirmed(state.created)

    async def _run_tool(self, call: ToolCall, state: ConversationState) -> Mapping[str, Any]:
        tool = self._tools.get(call.name)
        if tool is None:
            return tool_error(UNKNOWN_TOOL, f"There is no tool named {call.name!r}.")
        return await tool.handler(call.arguments, state)

    def _violations(self, reply: TextReply, stored: StoredQuote) -> tuple[Violation, ...]:
        context = build_narrative_context(stored.quote)
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
