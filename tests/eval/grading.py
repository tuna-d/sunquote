"""Mechanical grades for the final attempt of each Narrative scenario."""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from unicodedata import normalize

from sunquote.domain.narrative import (
    NarrativeContext,
    NarrativeDraft,
    NarrativeSource,
    Violation,
    ViolationKind,
    validate_narrative,
)
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.placeholders import PLACEHOLDER_PATTERN
from sunquote.domain.ports import NarrativeWriter
from sunquote.domain.service import generate_narrative
from tests.eval.scenarios import Scenario
from tests.fakes import NARRATIVE_TIME

GRADERS = (*(rule.value for rule in ViolationKind), "turkish_number_words")
_NUMBER_WORD = re.compile(
    r"\b(?:iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|altmış|"
    r"yetmiş|seksen|doksan|yüz|bin|milyon)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScenarioGrade:
    name: str
    source: NarrativeSource
    checks: dict[str, bool] | None

    @property
    def passed(self) -> bool:
        return (
            self.source is NarrativeSource.LLM
            and self.checks is not None
            and all(self.checks.values())
        )


class _ObservedWriter:
    """Keep the final attempt for diagnostics, even when Quote creation uses fallback."""

    def __init__(self, writer: NarrativeWriter, delay_seconds: float) -> None:
        self._writer = writer
        self._delay_seconds = delay_seconds
        self.final_draft: NarrativeDraft | None = None

    @property
    def model_name(self) -> str:
        return self._writer.model_name

    async def write(
        self, context: NarrativeContext, *, previous_violations: Sequence[Violation] = ()
    ) -> NarrativeDraft:
        self.final_draft = None
        if previous_violations:
            await asyncio.sleep(self._delay_seconds)
        draft = await self._writer.write(context, previous_violations=previous_violations)
        self.final_draft = draft
        return draft


def _grade_draft(draft: NarrativeDraft, context: NarrativeContext) -> dict[str, bool]:
    failed_rules = {violation.kind.value for violation in validate_narrative(draft, context)}
    for field in (draft.greeting, draft.summary, draft.options_comparison, draft.next_steps):
        prose = PLACEHOLDER_PATTERN.sub(" ", field or "")
        if _NUMBER_WORD.search(normalize("NFC", prose)):
            failed_rules.add("turkish_number_words")
            break
    return {name: name not in failed_rules for name in GRADERS}


async def evaluate_scenario(
    scenario: Scenario, *, writer: NarrativeWriter, budget_seconds: float, delay_seconds: float
) -> ScenarioGrade:
    quote = scenario.build()
    observed = _ObservedWriter(writer, delay_seconds)
    narrative = await generate_narrative(
        quote,
        writer=observed,
        generated_at=NARRATIVE_TIME,
        # Quote creation's shared budget plus the eval's one possible pause before a retry.
        budget_seconds=budget_seconds + delay_seconds,
    )
    draft = observed.final_draft
    checks = None if draft is None else _grade_draft(draft, build_narrative_context(quote))
    return ScenarioGrade(scenario.name, narrative.source, checks)


def _rate(passed: int, total: int) -> str:
    return f"{passed}/{total} ({passed / total:.1%})"


def format_report(results: Sequence[ScenarioGrade]) -> str:
    """Render the per-scenario table and rates across all scenarios."""
    # The numbered headings keep the table narrow. The rates below name each grader.
    headers = ("Scenario", "Source", *(str(i) for i in range(1, len(GRADERS) + 1)), "Result")
    width = max(len(headers[0]), *(len(result.name) for result in results))
    lines = [f"{headers[0]:<{width}}  {headers[1]:<8}  {'  '.join(headers[2:])}"]
    for result in results:
        cells = (
            "-" if result.checks is None else ("Y" if result.checks[name] else "N")
            for name in GRADERS
        )
        outcome = "PASS" if result.passed else "FAIL"
        lines.append(f"{result.name:<{width}}  {result.source:<8}  {'  '.join(cells)}  {outcome}")
    lines += [
        "",
        "Y = pass, N = fail, - = no draft from the final attempt (counts as a failure).",
        f"Overall: {_rate(sum(result.passed for result in results), len(results))}",
    ]
    for i, name in enumerate(GRADERS, start=1):
        passed = sum(result.checks is not None and result.checks[name] for result in results)
        lines.append(f"{i}. {name}: {_rate(passed, len(results))}")
    return "\n".join(lines)
