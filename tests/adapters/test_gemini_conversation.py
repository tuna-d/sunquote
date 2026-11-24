"""The Gemini ConversationModel against canned responses (no network).

The response fixtures in `recordings/gemini_conversation_*.json` follow the `generateContent`
function-calling response shape from Google's API reference (checked 2026-11-24): they were
written by hand, not captured, because recording needs a key. The real call is in
`test_gemini_integration.py`.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from sunquote.adapters.gemini_conversation import SYSTEM_INSTRUCTION, GeminiConversationModel
from sunquote.domain.conversation import (
    REPLY_MAX_CHARACTERS,
    ChatMessage,
    MessageRole,
    ReplyRejection,
    TextReply,
    ToolCall,
    ToolDeclaration,
    ToolExchange,
)
from sunquote.domain.errors import ConversationUnavailableError
from sunquote.domain.narrative import Violation, ViolationKind
from sunquote.domain.placeholders import PLACEHOLDER_PATTERN, known_placeholders

pytestmark = pytest.mark.anyio

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://gemini.example/v1beta"
MODEL = "gemini-test-model"
API_KEY = "AIza-test-secret-key-0123456789"
ENDPOINT_PATH = f"/v1beta/models/{MODEL}:generateContent"

PARAMETERS = {
    "type": "object",
    "properties": {"customer": {"type": "object"}},
    "required": ["customer"],
}
TOOLS = (ToolDeclaration("create_quote", "Create a Quote.", PARAMETERS),)
MESSAGES = (
    ChatMessage(MessageRole.USER, "Ayşe Yılmaz için teklif: Etimesgut."),
    ChatMessage(MessageRole.ASSISTANT, "Çatı bilgisini yazar mısınız?"),
    ChatMessage(MessageRole.USER, "40 m², güneye bakıyor, 30 derece."),
)


def recording(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=(RECORDINGS / name).read_bytes())


class FakeGemini:
    """Answers every request with `response` and remembers the requests."""

    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    @property
    def body(self) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(self.requests[-1].content)
        return parsed


def model_with(fake: FakeGemini) -> GeminiConversationModel:
    return GeminiConversationModel(
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
        api_key=API_KEY,
        model=MODEL,
        base_url=BASE_URL,
        timeout_seconds=5.0,
    )


async def ask(
    fake: FakeGemini,
    *,
    exchanges: tuple[ToolExchange, ...] = (),
    rejected_reply: ReplyRejection | None = None,
) -> Any:
    return await model_with(fake).respond(
        messages=MESSAGES,
        tools=TOOLS,
        exchanges=exchanges,
        rejected_reply=rejected_reply,
    )


def text_response(text: str) -> httpx.Response:
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    return httpx.Response(200, json=body)


# --- What the model answers ------------------------------------------------------------------


async def test_a_recorded_function_call_becomes_a_tool_call_with_its_signature() -> None:
    reply = await ask(FakeGemini(recording("gemini_conversation_function_call.json")))

    assert isinstance(reply, ToolCall)
    assert reply.name == "create_quote"
    assert reply.arguments["site"] == {"address": "Etimesgut, Ankara"}
    assert reply.arguments["roof"]["tilt_deg"] == 30
    assert reply.signature == "c2lnbmF0dXJlLTE="


async def test_a_recorded_ask_for_missing_fields_call_becomes_a_tool_call() -> None:
    reply = await ask(FakeGemini(recording("gemini_conversation_ask_for_missing_fields.json")))

    assert reply == ToolCall(
        name="ask_for_missing_fields",
        arguments={
            "fields": ["customer.name", "roof.tilt_deg", "consumption"],
            "question": "Müşterinin adı, çatının eğimi ve aylık tüketimi nedir?",
        },
        signature="c2lnbmF0dXJlLTI=",
    )


async def test_a_recorded_text_answer_becomes_a_text_reply() -> None:
    reply = await ask(FakeGemini(recording("gemini_conversation_text.json")))

    assert reply == TextReply(
        "Teklifiniz hazır. {quote_number} numaralı teklifte ilk seçenek "
        "{option_1_capacity_kwp} kWp gücündedir ve toplam {option_1_total_try} tutarındadır."
    )


async def test_thought_parts_are_not_part_of_the_reply() -> None:
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "thinking...", "thought": True}, {"text": "Merhaba"}]
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    )

    assert await ask(FakeGemini(response)) == TextReply("Merhaba")


async def test_only_the_first_of_several_parallel_function_calls_is_used() -> None:
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "create_quote", "args": {"a": 1}}},
                            {"functionCall": {"name": "ask_for_missing_fields", "args": {}}},
                        ]
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    )

    assert await ask(FakeGemini(response)) == ToolCall("create_quote", {"a": 1})


async def test_the_model_name_is_the_configured_one() -> None:
    model = model_with(FakeGemini(recording("gemini_conversation_text.json")))

    assert model.model_name == MODEL


# --- The request -----------------------------------------------------------------------------


async def test_the_request_goes_to_generate_content_of_the_model_with_the_key_in_a_header() -> None:
    fake = FakeGemini(recording("gemini_conversation_text.json"))

    await ask(fake)

    (request,) = fake.requests
    assert request.method == "POST"
    assert request.url.path == ENDPOINT_PATH
    assert request.headers["x-goog-api-key"] == API_KEY
    assert API_KEY not in str(request.url)
    assert API_KEY not in request.content.decode("utf-8")


async def test_the_request_carries_the_instruction_the_tools_and_the_messages() -> None:
    fake = FakeGemini(recording("gemini_conversation_text.json"))

    await ask(fake)

    body = fake.body
    assert body["systemInstruction"] == {"parts": [{"text": SYSTEM_INSTRUCTION}]}
    assert body["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "create_quote",
                    "description": "Create a Quote.",
                    "parametersJsonSchema": PARAMETERS,
                }
            ]
        }
    ]
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "Ayşe Yılmaz için teklif: Etimesgut."}]},
        {"role": "model", "parts": [{"text": "Çatı bilgisini yazar mısınız?"}]},
        {"role": "user", "parts": [{"text": "40 m², güneye bakıyor, 30 derece."}]},
    ]


async def test_an_earlier_tool_call_is_replayed_with_its_signature_and_result() -> None:
    fake = FakeGemini(recording("gemini_conversation_text.json"))
    call = ToolCall("create_quote", {"customer": {"name": "Ayşe"}}, signature="c2ln")
    exchange = ToolExchange(call, {"status": "created", "option_count": 2})

    await ask(fake, exchanges=(exchange,))

    contents = fake.body["contents"]
    assert contents[3:] == [
        {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": "create_quote",
                        "args": {"customer": {"name": "Ayşe"}},
                    },
                    "thoughtSignature": "c2ln",
                }
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "create_quote",
                        "response": {"status": "created", "option_count": 2},
                    }
                }
            ],
        },
    ]


async def test_a_call_without_a_signature_is_replayed_without_one() -> None:
    fake = FakeGemini(recording("gemini_conversation_text.json"))
    exchange = ToolExchange(ToolCall("create_quote", {}), {"status": "created"})

    await ask(fake, exchanges=(exchange,))

    assert "thoughtSignature" not in fake.body["contents"][3]["parts"][0]


async def test_a_rejected_reply_is_sent_back_with_its_violations() -> None:
    fake = FakeGemini(recording("gemini_conversation_text.json"))
    rejection = ReplyRejection(
        "Teklif 8 kWp.",
        (Violation(ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER, "reply", "a digit is written"),),
    )

    await ask(fake, rejected_reply=rejection)

    contents = fake.body["contents"]
    assert contents[3] == {"role": "model", "parts": [{"text": "Teklif 8 kWp."}]}
    assert contents[4]["role"] == "user"
    feedback = contents[4]["parts"][0]["text"]
    assert "digit_outside_placeholder" in feedback
    assert "a digit is written" in feedback


# --- Failures --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (recording("gemini_rate_limited.json", 429), "HTTP 429"),
        (httpx.Response(500, text="boom"), "HTTP 500"),
        (httpx.Response(503, text="overloaded"), "HTTP 503"),
        (httpx.Response(400, text="bad request"), "HTTP 400"),
        (recording("gemini_conversation_malformed.json"), "function call"),
        (recording("gemini_safety_blocked.json"), "blocked"),
        (httpx.Response(200, text="<html>not json</html>"), "not JSON"),
        (httpx.Response(200, json={"candidates": []}), "no candidate"),
        (httpx.Response(200, json=["a"]), "unexpected response"),
        (httpx.Response(200, json={"candidates": [{"finishReason": "STOP"}]}), "no text"),
        (
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "x"}]}, "finishReason": "SAFETY"}
                    ]
                },
            ),
            "SAFETY",
        ),
        (
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"functionCall": {"args": {}}}]},
                            "finishReason": "STOP",
                        }
                    ]
                },
            ),
            "function call",
        ),
    ],
    ids=[
        "429",
        "500",
        "503",
        "400",
        "malformed-function-call",
        "prompt-blocked",
        "body-not-json",
        "no-candidates",
        "body-not-an-object",
        "no-text",
        "candidate-blocked",
        "function-call-without-name",
    ],
)
async def test_every_failure_is_reported_as_conversation_unavailable(
    response: httpx.Response, reason: str
) -> None:
    with pytest.raises(ConversationUnavailableError) as error:
        await ask(FakeGemini(response))

    assert reason in error.value.reason
    assert API_KEY not in str(error.value)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx.ReadTimeout("slow"), "timed out"),
        (httpx.ConnectError("refused"), "ConnectError"),
    ],
)
async def test_timeouts_and_network_errors_are_reported_as_conversation_unavailable(
    failure: Exception, reason: str
) -> None:
    with pytest.raises(ConversationUnavailableError) as error:
        await ask(FakeGemini(failure))

    assert reason in error.value.reason


async def test_the_key_never_appears_in_an_error_even_when_the_server_echoes_it() -> None:
    echo = httpx.Response(
        400, json={"error": {"message": f"API key not valid: {API_KEY}", "status": "INVALID"}}
    )

    with pytest.raises(ConversationUnavailableError) as error:
        await ask(FakeGemini(echo))

    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(error.value)


async def test_the_key_never_appears_in_the_models_repr() -> None:
    model = model_with(FakeGemini(recording("gemini_conversation_text.json")))

    assert API_KEY not in repr(model)
    assert MODEL in repr(model)


# --- The instruction -------------------------------------------------------------------------

ORIENTATION_BEARINGS = {
    "kuzey": 0,
    "kuzeydoğu": 45,
    "doğu": 90,
    "güneydoğu": 135,
    "güney": 180,
    "güneybatı": 225,
    "batı": 270,
    "kuzeybatı": 315,
}


def test_the_instruction_is_english_and_states_the_assistants_rules() -> None:
    lowered = SYSTEM_INSTRUCTION.lower()

    assert "reply in turkish" in lowered
    assert "never estimate" in lowered
    assert "coordinates" in lowered
    assert "kwh over a bill" in lowered
    assert "placeholder" in lowered
    assert f"{REPLY_MAX_CHARACTERS} characters" in SYSTEM_INSTRUCTION


def test_the_instruction_maps_every_orientation_word_to_its_compass_bearing() -> None:
    for word, bearing in ORIENTATION_BEARINGS.items():
        assert f"{word} {bearing}" in SYSTEM_INSTRUCTION


def test_the_instruction_names_only_placeholders_of_the_vocabulary() -> None:
    named = set(PLACEHOLDER_PATTERN.findall(SYSTEM_INSTRUCTION))

    assert named
    assert named <= known_placeholders()


def test_the_instruction_lets_the_model_ask_for_the_required_subscriber_group() -> None:
    # subscriber_group is a required request field and a missing-field choice of the ask tool,
    # so the instruction must not call it "always residential".
    assert "always residential" not in SYSTEM_INSTRUCTION
    assert "subscriber_group is required" in SYSTEM_INSTRUCTION
    assert "unclear whether the Site is a home or a business" in SYSTEM_INSTRUCTION
