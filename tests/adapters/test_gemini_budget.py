"""Every Gemini request, from both adapters, draws from one shared budget at the transport."""

import httpx
import pytest

from sunquote.adapters.gemini import GeminiNarrativeWriter
from sunquote.adapters.gemini_conversation import GeminiConversationModel
from sunquote.domain.conversation import ChatMessage, MessageRole
from sunquote.domain.errors import GeminiBudgetExhaustedError
from sunquote.domain.gemini_budget import GeminiBudget
from tests.adapters.test_gemini import context
from tests.fakes import FixedClock, InMemoryCounterStore

pytestmark = pytest.mark.anyio

BASE_URL = "https://gemini.example/v1beta"
MESSAGES = (ChatMessage(MessageRole.USER, "Merhaba"),)


class CountingGemini:
    """Answers every request with HTTP 500 and counts how often it was contacted."""

    def __init__(self) -> None:
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        return httpx.Response(500)


def budget_of(limit: int) -> GeminiBudget:
    clock = FixedClock()
    return GeminiBudget(InMemoryCounterStore(clock=clock.now), clock, daily_limit=limit)


def adapters(
    gemini: CountingGemini, budget: GeminiBudget
) -> tuple[GeminiNarrativeWriter, GeminiConversationModel]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(gemini))
    writer = GeminiNarrativeWriter(
        client=client,
        api_key="k",
        model="m",
        base_url=BASE_URL,
        timeout_seconds=5.0,
        budget=budget,
    )
    model = GeminiConversationModel(
        client=client,
        api_key="k",
        model="m",
        base_url=BASE_URL,
        timeout_seconds=5.0,
        budget=budget,
    )
    return writer, model


async def test_calls_up_to_the_limit_reach_gemini_and_the_next_one_does_not() -> None:
    gemini = CountingGemini()
    writer, _ = adapters(gemini, budget_of(2))
    for _ in range(2):
        with pytest.raises(Exception, match="HTTP 500"):  # reaches Gemini, which answers 500
            await writer.write(context())

    with pytest.raises(GeminiBudgetExhaustedError):
        await writer.write(context())

    assert gemini.requests == 2


async def test_the_narrative_writer_and_the_conversation_model_share_one_budget() -> None:
    gemini = CountingGemini()
    writer, model = adapters(gemini, budget_of(2))
    with pytest.raises(Exception, match="HTTP 500"):
        await writer.write(context())
    with pytest.raises(Exception, match="HTTP 500"):
        await model.respond(messages=MESSAGES, tools=())

    with pytest.raises(GeminiBudgetExhaustedError):
        await model.respond(messages=MESSAGES, tools=())
    with pytest.raises(GeminiBudgetExhaustedError):
        await writer.write(context())

    assert gemini.requests == 2


async def test_an_adapter_without_a_budget_is_not_limited() -> None:
    gemini = CountingGemini()
    client = httpx.AsyncClient(transport=httpx.MockTransport(gemini))
    writer = GeminiNarrativeWriter(
        client=client, api_key="k", model="m", base_url=BASE_URL, timeout_seconds=5.0
    )

    for _ in range(5):
        with pytest.raises(Exception, match="HTTP 500"):
            await writer.write(context())

    assert gemini.requests == 5
