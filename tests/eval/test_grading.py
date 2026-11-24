from dataclasses import replace

import pytest

from sunquote.domain.errors import NarrativeUnavailableError
from sunquote.domain.narrative import NarrativeDraft, NarrativeSource, ViolationKind
from tests.eval.grading import GRADERS, evaluate_scenario, format_report
from tests.eval.scenarios import SCENARIOS
from tests.fakes import ScriptedNarrativeWriter

VALID_DRAFT = NarrativeDraft(
    greeting="Sayın {customer_name},",
    summary="Size uygun bir sistem öneriyoruz. Onarım giderleri teklife dahildir.",
    next_steps="Saha keşfi için görüşelim.",
)


@pytest.mark.anyio
async def test_a_valid_retry_passes_and_only_the_final_draft_is_graded() -> None:
    writer = ScriptedNarrativeWriter(replace(VALID_DRAFT, summary="7 kWp"), VALID_DRAFT)

    result = await evaluate_scenario(SCENARIOS[0], writer=writer, budget_seconds=1, delay_seconds=0)

    assert result.source is NarrativeSource.LLM
    assert result.passed
    assert [violation.kind for violation in writer.violations[1]] == [
        ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["İKİ seçenek", "(ÜÇ)", "KIRK", "MİLYON.", "ALTI"])
async def test_turkish_number_words_fail_the_eval_without_triggering_a_retry(text: str) -> None:
    writer = ScriptedNarrativeWriter(replace(VALID_DRAFT, next_steps=text))

    result = await evaluate_scenario(SCENARIOS[0], writer=writer, budget_seconds=1, delay_seconds=0)

    assert result.source is NarrativeSource.LLM
    assert not result.passed
    assert result.checks is not None
    assert {name for name, passed in result.checks.items() if not passed} == {
        "turkish_number_words"
    }
    assert len(writer.contexts) == 1


@pytest.mark.anyio
async def test_report_distinguishes_final_rejections_from_missing_drafts() -> None:
    invalid = replace(VALID_DRAFT, summary="{option_2_capacity_kwp}")
    invalid_writer = ScriptedNarrativeWriter(replace(VALID_DRAFT, summary="7 kWp"), invalid)
    unavailable_writer = ScriptedNarrativeWriter(invalid, NarrativeUnavailableError("HTTP 429"))
    rejected = await evaluate_scenario(
        SCENARIOS[0], writer=invalid_writer, budget_seconds=1, delay_seconds=0
    )
    unavailable = await evaluate_scenario(
        SCENARIOS[1], writer=unavailable_writer, budget_seconds=1, delay_seconds=0
    )

    assert rejected.source is unavailable.source is NarrativeSource.FALLBACK
    assert not rejected.passed and not unavailable.passed
    assert rejected.checks is not None
    assert {name for name, passed in rejected.checks.items() if not passed} == {
        "unavailable_placeholder"
    }
    assert unavailable.checks is None

    report = format_report([rejected, unavailable])
    assert "Overall: 0/2 (0.0%)" in report
    assert "digit_outside_placeholder: 1/2 (50.0%)" in report
    assert "unavailable_placeholder: 0/2 (0.0%)" in report


@pytest.mark.anyio
async def test_the_report_table_names_every_grader_in_its_header() -> None:
    writer = ScriptedNarrativeWriter(VALID_DRAFT)
    result = await evaluate_scenario(SCENARIOS[0], writer=writer, budget_seconds=1, delay_seconds=0)

    header, row = format_report([result]).splitlines()[:2]

    for name in GRADERS:
        assert name in header
    assert row.split().count("Y") == len(GRADERS)
    assert row.endswith("PASS")
