"""Gemini adapter: writes a Quote's Narrative through the `generateContent` REST endpoint.

It implements the `NarrativeWriter` port (ADR 0001). The model is told which placeholders it may
use and gets only the anonymised `NarrativeContext` as JSON, never a name, address or contact
detail. Its answer comes back as structured JSON (a schema of the four Narrative fields); the
domain validator decides whether the draft is acceptable, so this adapter only parses it.

Every failure (HTTP error, timeout, network error, blocked or malformed answer) is raised as
`NarrativeUnavailableError`. The API key travels in a header, never in the URL, and no error
message or `repr` contains it or the server's response body.

Default model: see `DEFAULT_GEMINI_MODEL`.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

import httpx

from sunquote.domain.errors import NarrativeUnavailableError
from sunquote.domain.narrative import (
    COMPARISON_FIELD,
    LENGTH_LIMITS,
    REQUIRED_FIELDS,
    NarrativeContext,
    NarrativeDraft,
    Violation,
)
from sunquote.domain.placeholders import (
    BARE_NUMBER_UNITS,
    CUSTOMER_NAME,
    MAX_OPTIONS,
    MONEY_SUFFIX,
    OPTION_PLACEHOLDERS,
    VALID_UNTIL,
    option_placeholder,
)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# `gemini-3.5-flash-lite`: stable, structured outputs supported, and "Free of charge" in the
# Free Tier column of Google's pricing page (https://ai.google.dev/gemini-api/docs/pricing,
# redirects to aistudio.google.com/docs/pricing), checked 2026-11-24. The free tier may use
# submitted content to improve Google's products, which is why only the anonymised context is
# sent. Re-check before changing it: free-tier availability changes between models and dates.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

# Placeholder names and units in the prompt come from the shared vocabulary, never from a copy.
_OPTION_EXAMPLE = option_placeholder(1, OPTION_PLACEHOLDERS[0])
_BARE_NUMBER_NAMES = ", ".join(BARE_NUMBER_UNITS)
_BARE_NUMBER_UNITS = ", ".join(BARE_NUMBER_UNITS.values())

SYSTEM_INSTRUCTION = f"""\
You write the prose of a solar panel quotation for a customer in Turkey. You are given an \
anonymised description of the quote as JSON and you return the Narrative as JSON with the \
fields greeting, summary, options_comparison and next_steps.

Language and tone
- Write in formal Turkish and address the customer as "siz" (never "sen").
- Be concise, warm and professional. Do not promise anything the description does not state.

Placeholders (the only way to refer to figures and to the customer)
- You never know the customer's name or any figure. Refer to them only through placeholders \
written in curly braces, exactly as listed in "available_placeholders", for example \
{{{CUSTOMER_NAME}}}. Use no other placeholder and do not invent one.
- A template replaces each placeholder with the real value, so write the surrounding sentence \
around it. Money placeholders (names ending in {MONEY_SUFFIX}) already include the currency. \
Placeholders for {_BARE_NUMBER_NAMES} are bare numbers: write the unit after them \
({_BARE_NUMBER_UNITS}).
- Write no digit anywhere outside a placeholder, and no number word either: no written-out \
numbers or counts such as "iki", "üç", "on" or "yirmi", and no ordinals such as \
"ikinci" or "üçüncü". Do not write dates, percentages or years yourself. Refer to the options \
without counting them: "ilk seçenek", "diğer seçenek", "daha büyük seçenek".

Content
- greeting: a short salutation that names the customer through {{{CUSTOMER_NAME}}}.
- summary: describe the proposed system in plain language using placeholders for capacity, \
production, price and payback. Explain what limited the size of the system, based on the \
binding_limit of each option: "roof" means the usable roof area, "consumption_target" means the \
system already covers the customer's yearly consumption, "contracted_power" means the grid \
connection agreement. Mention the roof orientation word when it helps. If \
annual_consumption_above_tier_threshold is true, part of the customer's consumption is billed at \
the higher tariff tier, which is why self-produced electricity is worth more. If an option has \
payback_beyond_lifetime true, it has no payback placeholder: say that its investment does not \
pay back within the system's lifetime and use no payback placeholder for it.
- options_comparison: write it only when system_options has two options, and then explain the \
trade-off between them using the "comparison" booleans (which option produces more, costs more \
and pays back sooner). When there is one option, return null for options_comparison.
- next_steps: the steps that follow the customer's acceptance (a site survey, the grid \
application, the installation), and the validity of the offer through {{{VALID_UNTIL}}}.

Length: stay within field_length_limits_characters for each field.

If "previous_attempt_violations" is present, your previous answer broke these rules. Fix every \
one of them in the new answer.

About the description: sizing_strategy "consumption_matched" means the system is sized to \
cover the yearly consumption and "roof_max" means as many panels as the roof fits. Options \
are numbered from 1 in the placeholders, for example {_OPTION_EXAMPLE}, and there are at \
most {MAX_OPTIONS}.
"""

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "greeting": {
            "type": "string",
            "description": (
                "Short formal Turkish salutation naming the customer by a placeholder. "
                f"At most {LENGTH_LIMITS['greeting']} characters."
            ),
        },
        "summary": {
            "type": "string",
            "description": (
                "Plain-language Turkish summary of the proposed system, with its binding limit. "
                f"At most {LENGTH_LIMITS['summary']} characters."
            ),
        },
        COMPARISON_FIELD: {
            "type": ["string", "null"],
            "description": (
                "Turkish comparison of the two options; null when there is only one option. "
                f"At most {LENGTH_LIMITS[COMPARISON_FIELD]} characters."
            ),
        },
        "next_steps": {
            "type": "string",
            "description": (
                "Turkish next steps after acceptance. "
                f"At most {LENGTH_LIMITS['next_steps']} characters."
            ),
        },
    },
    "required": list(REQUIRED_FIELDS),
    "additionalProperties": False,
}


def _user_content(context: NarrativeContext, violations: tuple[Violation, ...]) -> str:
    """The anonymised context as JSON, plus the previous attempt's violations on a retry."""
    comparison = None if context.comparison is None else asdict(context.comparison)
    content: dict[str, Any] = {
        "system_options": [
            {
                "number": number,
                "sizing_strategy": option.sizing_strategy.value,
                "binding_limit": option.binding_limit.value,
                "payback_beyond_lifetime": option.payback_beyond_lifetime,
            }
            for number, option in enumerate(context.options, start=1)
        ],
        "roof": {"type": context.roof_type.value, "orientation": context.orientation.value},
        "annual_consumption_above_tier_threshold": (
            context.annual_consumption_above_tier_threshold
        ),
        "comparison": comparison,
        "available_placeholders": list(context.available_placeholders),
        "field_length_limits_characters": LENGTH_LIMITS,
    }
    if violations:
        content["previous_attempt_violations"] = [
            {"kind": violation.kind.value, "field": violation.field, "detail": violation.detail}
            for violation in violations
        ]
    return json.dumps(content, ensure_ascii=False)


class GeminiNarrativeWriter:
    """Calls `<base_url>/models/<model>:generateContent` with a JSON response schema.

    The HTTP client is injected so tests can swap the transport. Every call carries its own
    timeout, whatever the client's defaults are. The API key is held privately and appears in
    no `repr`, log line or error.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return f"GeminiNarrativeWriter(model={self._model!r})"

    @property
    def model_name(self) -> str:
        return self._model

    async def write(
        self, context: NarrativeContext, *, previous_violations: Sequence[Violation] = ()
    ) -> NarrativeDraft:
        body = _request_body(context, tuple(previous_violations))
        payload = await self._post(body)
        return _parse_draft(payload)

    async def _post(self, body: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(
                self._endpoint,
                json=body,
                headers={"x-goog-api-key": self._api_key},
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            raise NarrativeUnavailableError("the request timed out") from None
        except httpx.TransportError as error:
            raise NarrativeUnavailableError(f"could not connect ({type(error).__name__})") from None
        if response.status_code != 200:
            # The body is deliberately not read: an error message could echo the key.
            raise NarrativeUnavailableError(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise NarrativeUnavailableError("the response body is not JSON") from None


def _request_body(context: NarrativeContext, violations: tuple[Violation, ...]) -> dict[str, Any]:
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": _user_content(context, violations)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": _RESPONSE_SCHEMA,
        },
    }


def _parse_draft(payload: Any) -> NarrativeDraft:
    """The draft inside a `generateContent` response, or `NarrativeUnavailableError`."""
    if not isinstance(payload, dict):
        raise NarrativeUnavailableError("unexpected response shape")
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise NarrativeUnavailableError(f"the prompt was blocked ({feedback['blockReason']})")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise NarrativeUnavailableError("the response has no candidate")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in (None, "STOP"):
        raise NarrativeUnavailableError(f"the answer was cut off or blocked ({finish_reason})")
    text = _candidate_text(candidate)
    try:
        fields = json.loads(text)
    except ValueError:
        raise NarrativeUnavailableError("the answer is not valid JSON") from None
    return _draft_from_fields(fields)


def _candidate_text(candidate: dict[str, Any]) -> str:
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    texts = [
        part["text"]
        for part in parts or []
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
    ]
    if not texts:
        raise NarrativeUnavailableError("the candidate has no text")
    return "".join(texts)


def _draft_from_fields(fields: Any) -> NarrativeDraft:
    mismatch = NarrativeUnavailableError("the answer does not match the schema")
    if not isinstance(fields, dict):
        raise mismatch
    for name in REQUIRED_FIELDS:
        if not isinstance(fields.get(name), str):
            raise mismatch
    comparison = fields.get(COMPARISON_FIELD)
    if comparison is not None and not isinstance(comparison, str):
        raise mismatch
    return NarrativeDraft(
        greeting=fields["greeting"],
        summary=fields["summary"],
        next_steps=fields["next_steps"],
        options_comparison=comparison,
    )
