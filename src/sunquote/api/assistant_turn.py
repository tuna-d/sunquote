"""One request of the quote assistant: the domain loop, the time budget and the Turkish reply.

The conversation policy lives in `sunquote.domain.assistant`. This layer gives it the tools, stops
it when the total time budget runs out (model calls and tool execution together, so a slow
geocoder or PVGIS counts too) and turns its outcome into the reply text: the model's own text
with the Quote's placeholders filled in, or a fixed Turkish template (`assistant_text`).

A run that is stopped while a tool is running can leave a Quote stored that the reply does not
mention; the reply then asks the Sales Rep to restate the information, as for any run that ends
without a Quote.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sunquote.api.assistant_text import (
    RESTATE_REPLY,
    fixed_confirmation,
    fixed_error_explanation,
    fixed_question,
)
from sunquote.api.narrative_text import placeholder_figures
from sunquote.api.option_views import option_views
from sunquote.domain.assistant import Assistant, AssistantOutcome, AssistantTools, OutcomeKind
from sunquote.domain.conversation import ChatMessage, MissingField
from sunquote.domain.placeholders import fill_placeholders
from sunquote.domain.ports import ConversationModel, StoredQuote


@dataclass(frozen=True, slots=True)
class AssistantTurn:
    """The reply for the Sales Rep, the Quote created in this request, if any, and the fields
    the reply asks for, if it is a question."""

    reply: str
    quote: StoredQuote | None
    missing_fields: tuple[MissingField, ...] = ()


async def run_assistant_turn(
    *,
    model: ConversationModel,
    tools: AssistantTools,
    messages: Sequence[ChatMessage],
    document_url: Callable[[UUID], str],
    budget_seconds: float,
) -> AssistantTurn:
    """Run the assistant for one request within `budget_seconds` in total.

    `document_url` turns a stored Quote's id into the link to its document, which the fixed
    confirmation shows. Raises `ConversationUnavailableError` when the model fails and no Quote
    exists. A run that ends without a reply in time is a reply, not an error.
    """
    assistant = Assistant(model=model, tools=tools)
    try:
        async with asyncio.timeout(budget_seconds):
            outcome = await assistant.run(messages)
    except TimeoutError:
        outcome = assistant.out_of_time()
    return _render(outcome, document_url)


def _render(outcome: AssistantOutcome, document_url: Callable[[UUID], str]) -> AssistantTurn:
    stored = outcome.quote
    # The Quote's figures are formatted once, for both the model's text and the confirmation.
    figures = placeholder_figures(stored, option_views(stored)) if stored is not None else {}
    match outcome.kind:
        case OutcomeKind.QUOTE_REPLY:
            assert outcome.text is not None
            reply = fill_placeholders(outcome.text, figures)
        case OutcomeKind.CONFIRMATION:
            assert stored is not None
            reply = fixed_confirmation(stored, document_url(stored.id), figures)
        case OutcomeKind.QUESTION | OutcomeKind.TEXT:
            assert outcome.text is not None
            reply = outcome.text
        case OutcomeKind.FIXED_QUESTION:
            reply = fixed_question(outcome.missing_fields)
        case OutcomeKind.ERROR_EXPLANATION:
            # A problem the template has no name for is the same as no explanation.
            reply = (
                fixed_error_explanation(outcome.problem) if outcome.problem is not None else None
            ) or RESTATE_REPLY
        case OutcomeKind.RESTATE:
            reply = RESTATE_REPLY
    return AssistantTurn(reply, stored, outcome.missing_fields)
