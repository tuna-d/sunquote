"""Drive and report on the endpoint's tool loop with an in-memory Quote service."""

import asyncio
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sunquote.api.assistant_tools import QuoteAssistantTools
from sunquote.api.assistant_turn import AssistantTurn, run_assistant_turn
from sunquote.domain.assistant import AssistantTools, ToolResult
from sunquote.domain.conversation import (
    CREATE_QUOTE,
    MAX_MODEL_CALLS,
    ChatMessage,
    MessageRole,
    ModelReply,
    ReplyRejection,
    ToolCall,
    ToolDeclaration,
    ToolExchange,
)
from sunquote.domain.errors import ConversationUnavailableError
from sunquote.domain.model import QuoteRequest
from sunquote.domain.narrative import Violation
from sunquote.domain.ports import ConversationModel, StoredQuote
from sunquote.domain.service import QuoteService
from tests.eval.extraction import ExtractionScenario, grade_extraction
from tests.eval.scenarios import SCENARIOS
from tests.fakes import NARRATIVE_TIME

# How often the eval repeats a Gemini call that failed (a 429 or an outage) before it counts.
MODEL_RETRIES = 2


class PacedRetryModel:
    """A ConversationModel that repeats a failed call after the eval's pacing delay.

    Free-tier limits answer a burst of requests with HTTP 429, which the model raises as
    `ConversationUnavailableError`. The eval waits `delay_seconds` and asks again, up to
    `MODEL_RETRIES` times, so a rate limit does not fail a scenario by itself.
    """

    def __init__(self, model: ConversationModel, *, delay_seconds: float) -> None:
        self._model = model
        self._delay_seconds = delay_seconds

    @property
    def model_name(self) -> str:
        return self._model.model_name

    async def respond(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDeclaration],
        exchanges: Sequence[ToolExchange] = (),
        rejected_reply: ReplyRejection | None = None,
    ) -> ModelReply:
        for attempt in range(MODEL_RETRIES + 1):
            try:
                return await self._model.respond(
                    messages=messages,
                    tools=tools,
                    exchanges=exchanges,
                    rejected_reply=rejected_reply,
                )
            except ConversationUnavailableError:
                if attempt == MODEL_RETRIES:
                    raise
                await asyncio.sleep(self._delay_seconds)
        raise AssertionError("unreachable")


def eval_budget_seconds(assistant_timeout_seconds: float, delay_seconds: float) -> float:
    """The normal time budget plus the pauses the eval adds: before each request, and after
    each failed one."""
    requests_per_turn = MAX_MODEL_CALLS * (1 + MODEL_RETRIES)
    pauses = requests_per_turn + MAX_MODEL_CALLS * MODEL_RETRIES
    return assistant_timeout_seconds + pauses * delay_seconds


class RecordingQuoteService:
    def __init__(self) -> None:
        self.arguments: list[dict[str, object]] = []
        self.requests: list[QuoteRequest] = []
        self.stored = StoredQuote(UUID(int=1), NARRATIVE_TIME, SCENARIOS[0].build())

    async def create_quote(self, request: QuoteRequest) -> StoredQuote:
        self.requests.append(request)
        return self.stored

    def tools(self) -> AssistantTools:
        # The tools only need create_quote; the fake does not initialise real providers.
        return _RecordingTools(self, QuoteAssistantTools(cast(QuoteService, self)))


class _RecordingTools:
    """The assistant's tools, recording the `create_quote` arguments as the model wrote them,
    before validation rejects a call or drops unexpected fields."""

    def __init__(self, service: RecordingQuoteService, tools: QuoteAssistantTools) -> None:
        self._service = service
        self._tools = tools

    @property
    def declarations(self) -> Sequence[ToolDeclaration]:
        return self._tools.declarations

    async def run(self, call: ToolCall) -> ToolResult:
        if call.name == CREATE_QUOTE:
            self._service.arguments.append(dict(call.arguments))
        return await self._tools.run(call)

    def rejection(self, violations: Sequence[Violation]) -> ToolResult:
        return self._tools.rejection(violations)


async def evaluate_extraction(
    scenario: ExtractionScenario, *, model: ConversationModel, budget_seconds: float
) -> dict[str, bool]:
    service = RecordingQuoteService()
    history: list[ChatMessage] = []
    outcome: AssistantTurn | None = None
    failure = None
    for turn, message in enumerate(scenario.messages, start=1):
        history.append(ChatMessage(MessageRole.USER, message))
        try:
            outcome = await run_assistant_turn(
                model=model,
                tools=service.tools(),
                messages=history,
                document_url=lambda quote_id: f"/quotes/{quote_id}/document",
                budget_seconds=budget_seconds,
            )
        except ConversationUnavailableError:
            failure = "Gemini response"
            break
        if turn == len(scenario.messages):
            break
        if service.arguments:
            failure = "create_quote called before final turn"
            break
        history.append(ChatMessage(MessageRole.ASSISTANT, outcome.reply))

    grades = grade_extraction(
        service.arguments,
        outcome.missing_fields if outcome is not None else (),
        expected_arguments=scenario.arguments,
        expected_missing_fields=scenario.missing_fields or (),
    )
    if failure is not None:
        return dict.fromkeys([*grades, failure], False)
    if scenario.arguments is not None:
        grades["create_quote"] &= (
            len(service.requests) == 1 and outcome is not None and outcome.quote is not None
        )
    return grades


def format_extraction_report(results: Sequence[tuple[str, dict[str, bool]]]) -> str:
    lines = ["Scenario | Result | Passed fields | Failed fields", "--- | --- | --- | ---"]
    by_field: dict[str, list[bool]] = {}
    for name, grades in results:
        passed = ", ".join(field for field, ok in grades.items() if ok) or "-"
        failed = ", ".join(field for field, ok in grades.items() if not ok) or "-"
        lines.append(f"{name} | {'PASS' if all(grades.values()) else 'FAIL'} | {passed} | {failed}")
        for field, ok in grades.items():
            by_field.setdefault(field, []).append(ok)
    lines.extend(["", "Field | Passed / Scored | Rate", "--- | --- | ---"])
    for field, scores in sorted(by_field.items()):
        lines.append(f"{field} | {sum(scores)}/{len(scores)} | {sum(scores) / len(scores):.1%}")
    passed_count = sum(all(grades.values()) for _, grades in results)
    lines.append(f"\nOverall: {passed_count}/{len(results)} ({passed_count / len(results):.1%})")
    return "\n".join(lines)
