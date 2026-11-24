"""Run the Narrative evaluation against Gemini with `uv run pytest -m eval`."""

import asyncio

import httpx
import pytest

from sunquote.adapters.gemini import GeminiNarrativeWriter
from tests.eval.grading import ScenarioGrade, evaluate_scenario, format_report
from tests.eval.scenarios import SCENARIOS
from tests.eval.settings import EvalSettings


@pytest.mark.eval
@pytest.mark.anyio
async def test_gemini_narrative_eval(capsys: pytest.CaptureFixture[str]) -> None:
    settings = EvalSettings()
    if settings.gemini_api_key is None:
        pytest.skip(
            "Set SUNQUOTE_GEMINI_API_KEY in the environment or .env to run the Narrative eval"
        )

    results: list[ScenarioGrade] = []
    async with httpx.AsyncClient() as client:
        writer = GeminiNarrativeWriter(
            client=client,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.gemini_timeout_seconds,
        )
        for scenario in SCENARIOS:
            if results:
                await asyncio.sleep(settings.eval_delay_seconds)
            results.append(
                await evaluate_scenario(
                    scenario,
                    writer=writer,
                    budget_seconds=settings.narrative_timeout_seconds,
                    delay_seconds=settings.eval_delay_seconds,
                )
            )

    with capsys.disabled():
        print(f"\nGemini Narrative evaluation ({writer.model_name})\n{format_report(results)}")
    pass_rate = sum(result.passed for result in results) / len(results)
    assert pass_rate >= 0.90, f"Narrative eval pass rate {pass_rate:.1%} is below 90%"
