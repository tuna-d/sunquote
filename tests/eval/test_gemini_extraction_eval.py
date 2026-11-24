"""Run the extraction evaluation against Gemini with `uv run pytest -m eval`."""

import asyncio

import httpx
import pytest

from sunquote.adapters.gemini_conversation import GeminiConversationModel
from sunquote.domain.conversation import MAX_MODEL_CALLS
from tests.eval.extraction import load_extraction_scenarios
from tests.eval.extraction_runner import evaluate_extraction, format_extraction_report
from tests.eval.settings import EvalSettings


@pytest.mark.eval
@pytest.mark.anyio
async def test_gemini_extraction_eval(capsys: pytest.CaptureFixture[str]) -> None:
    settings = EvalSettings()
    if settings.gemini_api_key is None:
        pytest.skip(
            "Set SUNQUOTE_GEMINI_API_KEY in the environment or .env to run the extraction eval"
        )

    sent_request = False

    async def pace_request(request: httpx.Request) -> None:
        nonlocal sent_request
        if sent_request:
            await asyncio.sleep(settings.eval_delay_seconds)
        sent_request = True

    # Preserve the normal time budget for the model and tools after allowing for pacing.
    budget = settings.assistant_timeout_seconds + MAX_MODEL_CALLS * settings.eval_delay_seconds
    results: list[tuple[str, dict[str, bool]]] = []
    async with httpx.AsyncClient(event_hooks={"request": [pace_request]}) as client:
        model = GeminiConversationModel(
            client=client,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.gemini_timeout_seconds,
        )
        for scenario in load_extraction_scenarios():
            grades = await evaluate_extraction(scenario, model=model, budget_seconds=budget)
            results.append((scenario.name, grades))

    with capsys.disabled():
        print(f"\nGemini extraction evaluation ({model.model_name})")
        print(format_extraction_report(results))
    pass_rate = sum(all(grades.values()) for _, grades in results) / len(results)
    assert pass_rate >= 0.90, f"Extraction eval pass rate {pass_rate:.1%} is below 90%"
