"""Drive and report on the endpoint's tool loop with an in-memory Quote service."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from sunquote.api.assistant_loop import Assistant
from sunquote.api.assistant_tools import (
    AssistantTool,
    ConversationState,
    ask_for_missing_fields_tool,
    create_quote_tool,
)
from sunquote.domain.conversation import ChatMessage, MessageRole
from sunquote.domain.errors import ConversationUnavailableError
from sunquote.domain.model import QuoteRequest
from sunquote.domain.ports import ConversationModel, StoredQuote
from sunquote.domain.service import QuoteService
from tests.eval.extraction import ExtractionScenario, grade_extraction
from tests.eval.scenarios import SCENARIOS
from tests.fakes import NARRATIVE_TIME


class RecordingQuoteService:
    def __init__(self) -> None:
        self.arguments: list[dict[str, object]] = []
        self.requests: list[QuoteRequest] = []
        self.stored = StoredQuote(UUID(int=1), NARRATIVE_TIME, SCENARIOS[0].build())

    async def create_quote(self, request: QuoteRequest) -> StoredQuote:
        self.requests.append(request)
        return self.stored

    def tool(self) -> AssistantTool:
        # The tool only needs create_quote; the fake does not initialise real providers.
        tool = create_quote_tool(cast(QuoteService, self))

        async def capture(
            arguments: Mapping[str, object], state: ConversationState
        ) -> dict[str, Any]:
            # Record before validation, which can reject a call or drop unexpected fields.
            self.arguments.append(dict(arguments))
            return await tool.handler(arguments, state)

        return replace(tool, handler=capture)


async def evaluate_extraction(
    scenario: ExtractionScenario, *, model: ConversationModel, budget_seconds: float
) -> dict[str, bool]:
    service = RecordingQuoteService()
    assistant = Assistant(
        model=model,
        tools=[service.tool(), ask_for_missing_fields_tool()],
        document_url=lambda quote_id: f"/quotes/{quote_id}/document",
        budget_seconds=budget_seconds,
    )
    history: list[ChatMessage] = []
    outcome = None
    failure = None
    for turn, message in enumerate(scenario.messages, start=1):
        history.append(ChatMessage(MessageRole.USER, message))
        try:
            outcome = await assistant.run(history)
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
