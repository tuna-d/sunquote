"""What the Gemini adapters share: the `generateContent` HTTP call and the first candidate.

Each adapter passes its own error factory, so a failure is raised as that adapter's typed error.
Every request draws one unit from the daily budget first (ADR 0007), so one count covers the
Narrative's attempts, its retries and the Assistant's calls; a spent budget raises
`GeminiBudgetExhaustedError` before anything is sent.
The API key travels in a header, never in the URL, and no error message contains it or the
server's response body.
"""

from collections.abc import Callable
from typing import Any

import httpx

from sunquote.domain.gemini_budget import GeminiBudget

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Builds the adapter's typed error from a short reason; the adapter's code raises its result.
Failure = Callable[[str], Exception]


def generate_content_endpoint(base_url: str, model: str) -> str:
    return f"{base_url.rstrip('/')}/models/{model}:generateContent"


async def post_generate_content(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    api_key: str,
    body: dict[str, Any],
    timeout_seconds: float,
    fail: Failure,
    budget: GeminiBudget | None = None,
) -> Any:
    """POST `body` to `endpoint` and return the parsed JSON, or raise `fail(reason)`.

    With a `budget`, the request is counted first and refused when the day's budget is spent.
    """
    if budget is not None:
        await budget.spend()
    try:
        response = await client.post(
            endpoint,
            json=body,
            headers={"x-goog-api-key": api_key},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException:
        raise fail("the request timed out") from None
    except httpx.TransportError as error:
        raise fail(f"could not connect ({type(error).__name__})") from None
    if response.status_code != 200:
        # The body is deliberately not read: an error message could echo the key.
        raise fail(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise fail("the response body is not JSON") from None


def first_candidate(payload: Any, fail: Failure) -> dict[str, Any]:
    """The first candidate of a `generateContent` response that finished normally."""
    if not isinstance(payload, dict):
        raise fail("unexpected response shape")
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise fail(f"the prompt was blocked ({feedback['blockReason']})")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise fail("the response has no candidate")
    candidate: dict[str, Any] = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in (None, "STOP"):
        raise fail(f"the answer was cut off or blocked ({finish_reason})")
    return candidate


def candidate_parts(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """The candidate's content parts, without the model's thought summaries."""
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    return [part for part in parts or [] if isinstance(part, dict) and not part.get("thought")]
