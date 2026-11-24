"""The Gemini NarrativeWriter against canned responses (no network).

The response fixtures in `recordings/gemini_*.json` follow the `generateContent` response shape
from Google's API reference (checked 2026-11-24): they were written by hand, not captured, because
recording needs a key. The real call is in `test_gemini_integration.py`.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from sunquote.adapters.gemini import GeminiNarrativeWriter
from sunquote.domain.errors import NarrativeUnavailableError
from sunquote.domain.model import RoofType
from sunquote.domain.narrative import (
    LENGTH_LIMITS,
    NarrativeContext,
    NarrativeDraft,
    OptionComparison,
    OptionContext,
    Orientation,
    Violation,
    ViolationKind,
)
from sunquote.domain.placeholders import available_placeholders
from sunquote.domain.sizing import BindingLimit, SizingStrategy

pytestmark = pytest.mark.anyio

RECORDINGS = Path(__file__).parent / "recordings"
BASE_URL = "https://gemini.example/v1beta"
MODEL = "gemini-test-model"
API_KEY = "AIza-test-secret-key-0123456789"
ENDPOINT_PATH = f"/v1beta/models/{MODEL}:generateContent"


def recording(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=(RECORDINGS / name).read_bytes())


def text_response(text: str) -> httpx.Response:
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    return httpx.Response(200, json=body)


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

    @property
    def user_content(self) -> dict[str, Any]:
        text = self.body["contents"][0]["parts"][0]["text"]
        parsed: dict[str, Any] = json.loads(text)
        return parsed


def writer_with(fake: FakeGemini, *, timeout_seconds: float = 5.0) -> GeminiNarrativeWriter:
    return GeminiNarrativeWriter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
        api_key=API_KEY,
        model=MODEL,
        base_url=BASE_URL,
        timeout_seconds=timeout_seconds,
    )


def context(option_count: int = 2) -> NarrativeContext:
    options = (
        OptionContext(SizingStrategy.CONSUMPTION_MATCHED, BindingLimit.ROOF, False),
        OptionContext(SizingStrategy.ROOF_MAX, BindingLimit.ROOF, True),
    )[:option_count]
    return NarrativeContext(
        options=options,
        roof_type=RoofType.PITCHED,
        orientation=Orientation.SOUTH_EAST,
        annual_consumption_above_tier_threshold=True,
        comparison=(
            OptionComparison(
                second_option_produces_more=True,
                second_option_costs_more=True,
                second_option_pays_back_sooner=False,
            )
            if option_count == 2
            else None
        ),
        available_placeholders=tuple(
            sorted(
                available_placeholders(
                    payback_beyond_lifetime=[option.payback_beyond_lifetime for option in options]
                )
            )
        ),
    )


# --- Success ---------------------------------------------------------------------------------


async def test_a_recorded_success_response_becomes_a_draft() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    draft = await writer_with(fake).write(context())

    assert draft == NarrativeDraft(
        greeting="Merhaba {customer_name}, teklifiniz hazır.",
        summary=(
            "Önerilen {option_1_capacity_kwp} kWp güçteki sistem yılda "
            "{option_1_annual_production_kwh} kWh üretir. Çatınızın alanı sistemin boyutunu "
            "belirledi."
        ),
        next_steps="Önce bir keşif ziyareti planlanır. Teklif {valid_until} tarihine kadar "
        "geçerlidir.",
        options_comparison=(
            "Daha büyük ikinci seçenek {option_2_total_try} tutarındadır ve geri ödemesi "
            "{option_2_payback_years} yıldır."
        ),
    )


async def test_a_null_or_missing_comparison_is_no_comparison() -> None:
    for fields in (
        {"greeting": "a", "summary": "b", "next_steps": "c", "options_comparison": None},
        {"greeting": "a", "summary": "b", "next_steps": "c"},
    ):
        fake = FakeGemini(text_response(json.dumps(fields)))

        draft = await writer_with(fake).write(context(option_count=1))

        assert draft.options_comparison is None


async def test_the_writer_reports_the_configured_model_name() -> None:
    writer = writer_with(FakeGemini(recording("gemini_generate_content_success.json")))

    assert writer.model_name == MODEL


# --- The request -----------------------------------------------------------------------------


async def test_the_request_goes_to_generate_content_of_the_model_with_the_key_in_a_header() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context())

    (request,) = fake.requests
    assert request.method == "POST"
    assert request.url.path == ENDPOINT_PATH
    assert request.headers["x-goog-api-key"] == API_KEY
    # Never in the URL, which ends up in logs and error messages.
    assert API_KEY not in str(request.url)


async def test_the_request_asks_for_json_with_a_schema_of_the_four_narrative_fields() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context())

    output_format = fake.body["generationConfig"]["responseFormat"]["text"]
    assert output_format["mimeType"] == "APPLICATION_JSON"
    schema = output_format["schema"]
    assert schema["type"] == "object"
    assert set(schema["properties"]) == {"greeting", "summary", "options_comparison", "next_steps"}
    assert set(schema["required"]) == {"greeting", "summary", "next_steps"}
    assert schema["properties"]["options_comparison"]["type"] == ["string", "null"]
    assert schema["properties"]["greeting"]["type"] == "string"


async def test_the_system_instruction_is_english_and_states_the_rules() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context())

    instruction = fake.body["systemInstruction"]["parts"][0]["text"]
    lowered = instruction.lower()
    assert "turkish" in lowered
    assert '"siz"' in instruction
    assert "placeholder" in lowered
    assert "digit" in lowered
    assert "number word" in lowered
    assert "options_comparison" in instruction
    assert "binding_limit" in instruction


async def test_the_user_content_is_the_anonymised_context_as_json() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context())

    sent = fake.user_content
    assert sent["roof"] == {"type": "pitched", "orientation": "south-east"}
    assert sent["annual_consumption_above_tier_threshold"] is True
    assert sent["system_options"] == [
        {
            "number": 1,
            "sizing_strategy": "consumption_matched",
            "binding_limit": "roof",
            "payback_beyond_lifetime": False,
        },
        {
            "number": 2,
            "sizing_strategy": "roof_max",
            "binding_limit": "roof",
            "payback_beyond_lifetime": True,
        },
    ]
    assert sent["comparison"] == {
        "second_option_produces_more": True,
        "second_option_costs_more": True,
        "second_option_pays_back_sooner": False,
    }
    assert sent["available_placeholders"] == list(context().available_placeholders)
    assert "option_2_payback_years" not in sent["available_placeholders"]
    assert sent["field_length_limits_characters"] == LENGTH_LIMITS
    assert "previous_attempt_violations" not in sent


async def test_a_single_option_context_sends_no_comparison() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context(option_count=1))

    assert fake.user_content["comparison"] is None
    assert len(fake.user_content["system_options"]) == 1


async def test_the_request_carries_no_personal_data_beyond_the_customer_name_placeholder() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))

    await writer_with(fake).write(context())

    sent = fake.requests[0].content.decode("utf-8")
    # The context type has no field for them; this guards the request as a whole: no name,
    # address, coordinates, phone or email can appear, only the placeholder name.
    for personal in ("Şule", "Öztürk", "Anıtkabir", "Ankara", "39.93", "@", "+90"):
        assert personal not in sent
    assert "{customer_name}" in sent


async def test_a_retry_adds_the_previous_attempts_violations() -> None:
    fake = FakeGemini(recording("gemini_generate_content_success.json"))
    violations = (
        Violation(ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER, "summary", "a digit is written"),
        Violation(ViolationKind.TOO_LONG, "greeting", "250 characters; the limit is 200"),
    )

    await writer_with(fake).write(context(), previous_violations=violations)

    assert fake.user_content["previous_attempt_violations"] == [
        {"kind": "digit_outside_placeholder", "field": "summary", "detail": "a digit is written"},
        {"kind": "too_long", "field": "greeting", "detail": "250 characters; the limit is 200"},
    ]


# --- Failures --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (recording("gemini_rate_limited.json", 429), "HTTP 429"),
        (httpx.Response(500, text="boom"), "HTTP 500"),
        (httpx.Response(503, text="overloaded"), "HTTP 503"),
        (httpx.Response(400, text="bad request"), "HTTP 400"),
        (httpx.Response(403, text="forbidden"), "HTTP 403"),
        (recording("gemini_malformed_json.json"), "not valid JSON"),
        (recording("gemini_schema_mismatch.json"), "schema"),
        (recording("gemini_safety_blocked.json"), "blocked"),
        (httpx.Response(200, text="<html>not json</html>"), "not JSON"),
        (httpx.Response(200, json={"candidates": []}), "no candidate"),
        (httpx.Response(200, json=["a"]), "unexpected response"),
        (text_response('["a", "b"]'), "schema"),
        (text_response('{"greeting": "a", "summary": "b"}'), "schema"),
        (
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "{}"}]}, "finishReason": "SAFETY"}
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
                        {"content": {"parts": [{"text": "{"}]}, "finishReason": "MAX_TOKENS"}
                    ]
                },
            ),
            "MAX_TOKENS",
        ),
        (httpx.Response(200, json={"candidates": [{"finishReason": "STOP"}]}), "no text"),
    ],
    ids=[
        "429",
        "500",
        "503",
        "400",
        "403",
        "malformed-json",
        "schema-mismatch",
        "prompt-blocked",
        "body-not-json",
        "no-candidates",
        "body-not-an-object",
        "text-not-an-object",
        "missing-required-field",
        "candidate-blocked",
        "truncated",
        "no-text",
    ],
)
async def test_every_failure_is_reported_as_narrative_unavailable(
    response: httpx.Response, reason: str
) -> None:
    with pytest.raises(NarrativeUnavailableError) as error:
        await writer_with(FakeGemini(response)).write(context())

    assert reason in error.value.reason
    assert API_KEY not in str(error.value)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx.ReadTimeout("slow"), "timed out"),
        (httpx.ConnectError("refused"), "ConnectError"),
        (httpx.ReadError("reset"), "ReadError"),
    ],
)
async def test_timeouts_and_network_errors_are_reported_as_narrative_unavailable(
    failure: Exception, reason: str
) -> None:
    with pytest.raises(NarrativeUnavailableError) as error:
        await writer_with(FakeGemini(failure)).write(context())

    assert reason in error.value.reason


async def test_the_key_never_appears_in_an_error_even_when_the_server_echoes_it() -> None:
    echo = httpx.Response(
        400, json={"error": {"message": f"API key not valid: {API_KEY}", "status": "INVALID"}}
    )

    with pytest.raises(NarrativeUnavailableError) as error:
        await writer_with(FakeGemini(echo)).write(context())

    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(error.value)
    assert API_KEY not in error.value.reason


async def test_the_key_never_appears_in_the_writers_repr() -> None:
    writer = writer_with(FakeGemini(recording("gemini_generate_content_success.json")))

    assert API_KEY not in repr(writer)
    assert API_KEY not in str(writer)
    assert MODEL in repr(writer)
