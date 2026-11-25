"""The Narrative: what a writer returns, what is stored, and the rules a draft must obey.

The prose slots hold text and `{placeholders}` only (ADR 0001). `validate_narrative` checks a
draft mechanically against the anonymised `NarrativeContext`; the domain writes no prose.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sunquote.domain.model import RoofType
from sunquote.domain.placeholders import MAX_OPTIONS, PLACEHOLDER_PATTERN, known_placeholders
from sunquote.domain.sizing import BindingLimit, SizingStrategy

REQUIRED_FIELDS = ("greeting", "summary", "next_steps")
COMPARISON_FIELD = "options_comparison"
LENGTH_LIMITS = {
    "greeting": 200,
    "summary": 1200,
    COMPARISON_FIELD: 1200,
    "next_steps": 800,
}


def has_comparison(option_count: int) -> bool:
    """Whether a Quote with `option_count` System Options gets an options comparison: it
    compares two options, so a Quote with one has none."""
    return option_count == MAX_OPTIONS


class Orientation(StrEnum):
    """Where a Roof faces: an 8-point compass word, or `flat` for a flat Roof."""

    NORTH = "north"
    NORTH_EAST = "north-east"
    EAST = "east"
    SOUTH_EAST = "south-east"
    SOUTH = "south"
    SOUTH_WEST = "south-west"
    WEST = "west"
    NORTH_WEST = "north-west"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class OptionContext:
    sizing_strategy: SizingStrategy
    binding_limit: BindingLimit
    payback_beyond_lifetime: bool


@dataclass(frozen=True, slots=True)
class OptionComparison:
    """How the second System Option compares with the first. Ties are false."""

    second_option_produces_more: bool
    second_option_costs_more: bool
    second_option_pays_back_sooner: bool


@dataclass(frozen=True, slots=True)
class NarrativeContext:
    """What a writer is told about a Quote: structure without figures or personal data.

    There is deliberately no field for the Customer's name, Address, Coordinates, phone or
    email. `available_placeholders` is sorted, so the same Quote gives the same context.
    """

    options: tuple[OptionContext, ...]
    roof_type: RoofType
    orientation: Orientation
    annual_consumption_above_tier_threshold: bool
    comparison: OptionComparison | None
    available_placeholders: tuple[str, ...]

    @property
    def option_count(self) -> int:
        return len(self.options)


@dataclass(frozen=True, slots=True)
class NarrativeDraft:
    """The four prose slots, as text with placeholders. `options_comparison` is for two
    System Options only."""

    greeting: str
    summary: str
    next_steps: str
    options_comparison: str | None = None


class ViolationKind(StrEnum):
    DIGIT_OUTSIDE_PLACEHOLDER = "digit_outside_placeholder"
    DIGIT_NOT_IN_USER_MESSAGES = "digit_not_in_user_messages"
    UNKNOWN_PLACEHOLDER = "unknown_placeholder"
    UNAVAILABLE_PLACEHOLDER = "unavailable_placeholder"
    MISSING_FIELD = "missing_field"
    UNEXPECTED_COMPARISON = "unexpected_comparison"
    TOO_LONG = "too_long"


@dataclass(frozen=True, slots=True)
class Violation:
    """One broken rule: which, in which field, and a short explanation a writer can act on."""

    kind: ViolationKind
    field: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        """The violation as the JSON object a model is told (`kind`, `field`, `detail`)."""
        return {"kind": self.kind.value, "field": self.field, "detail": self.detail}


class NarrativeSource(StrEnum):
    LLM = "llm"
    FALLBACK = "fallback"


class FallbackReason(StrEnum):
    """Why a `fallback` Narrative was recorded, when the cause is worth keeping."""

    BUDGET_SPENT = "budget_spent"
    """The day's Gemini budget was spent, so the writer was not asked."""


@dataclass(frozen=True, slots=True)
class NarrativeRecord:
    """The Narrative as stored with a Quote.

    `llm`: the writer's validated `draft` and the `model` that wrote it. `fallback`: no draft
    and no model, so the template's fixed text is shown. `generated_at` is when the Narrative
    step ran; it is None only for Quotes stored before the step existed. `fallback_reason` names
    the cause of a `fallback` when one is recorded (the spent budget); it is None otherwise.
    """

    source: NarrativeSource
    draft: NarrativeDraft | None
    model: str | None
    generated_at: datetime | None
    fallback_reason: FallbackReason | None = None

    def __post_init__(self) -> None:
        if self.source is NarrativeSource.LLM:
            if self.draft is None or not self.model:
                raise ValueError("an llm Narrative needs a draft and a model name")
        elif self.draft is not None or self.model is not None:
            raise ValueError("a fallback Narrative has no draft and no model name")
        if self.source is NarrativeSource.LLM and self.fallback_reason is not None:
            raise ValueError("only a fallback Narrative has a fallback reason")


# Quotes stored before the Narrative step read back as this.
NO_NARRATIVE = NarrativeRecord(
    source=NarrativeSource.FALLBACK, draft=None, model=None, generated_at=None
)


def _fields(draft: NarrativeDraft) -> tuple[tuple[str, str | None], ...]:
    return (
        ("greeting", draft.greeting),
        ("summary", draft.summary),
        (COMPARISON_FIELD, draft.options_comparison),
        ("next_steps", draft.next_steps),
    )


def validate_placeholder_syntax(
    text: str, *, field: str, available_placeholders: Collection[str]
) -> tuple[Violation, ...]:
    """The placeholder rules of one text: no unknown name, no name the Quote cannot fill and no
    unbalanced curly brace. With no available placeholders any `{...}` is a violation, which is
    the rule for a text that has no Quote to fill from."""
    violations: list[Violation] = []
    available = set(available_placeholders)
    known = known_placeholders()
    for name in dict.fromkeys(PLACEHOLDER_PATTERN.findall(text)):
        if name not in known:
            violations.append(
                Violation(ViolationKind.UNKNOWN_PLACEHOLDER, field, f"unknown placeholder {name!r}")
            )
        elif name not in available:
            violations.append(
                Violation(
                    ViolationKind.UNAVAILABLE_PLACEHOLDER,
                    field,
                    f"placeholder {name!r} is not available for this Quote",
                )
            )
    outside = PLACEHOLDER_PATTERN.sub("", text)
    if "{" in outside or "}" in outside:
        violations.append(
            Violation(ViolationKind.UNKNOWN_PLACEHOLDER, field, "unbalanced curly brace")
        )
    return tuple(violations)


def validate_text(
    text: str, *, field: str, available_placeholders: Collection[str], max_length: int
) -> tuple[Violation, ...]:
    """Every per-text rule `text` breaks: digits outside placeholders, unknown or unavailable
    placeholders, unbalanced curly braces and length. `field` names the text in the violations.

    The Narrative's slots use it, and so does any other text that may refer to a Quote's
    figures only through placeholders (the assistant's reply). A digit is a decimal digit: the
    superscript of "m²" is not one.
    """
    violations = list(
        validate_placeholder_syntax(
            text, field=field, available_placeholders=available_placeholders
        )
    )
    outside = PLACEHOLDER_PATTERN.sub("", text)
    if any(character.isdecimal() for character in outside):
        violations.append(
            Violation(
                ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER,
                field,
                "a digit is written outside a placeholder; refer to figures by placeholder",
            )
        )
    if len(text) > max_length:
        violations.append(
            Violation(
                ViolationKind.TOO_LONG,
                field,
                f"{len(text)} characters; the limit is {max_length}",
            )
        )
    return tuple(violations)


def validate_narrative(draft: NarrativeDraft, context: NarrativeContext) -> tuple[Violation, ...]:
    """Every rule `draft` breaks for the Quote `context` describes; empty when it is valid.

    A blank `options_comparison` counts as absent.
    """
    violations: list[Violation] = []
    needs_comparison = has_comparison(context.option_count)
    for field, text in _fields(draft):
        if text is None or not text.strip():
            if field != COMPARISON_FIELD or needs_comparison:
                violations.append(Violation(ViolationKind.MISSING_FIELD, field, "required"))
        elif field == COMPARISON_FIELD and not needs_comparison:
            violations.append(
                Violation(
                    ViolationKind.UNEXPECTED_COMPARISON,
                    field,
                    "must be absent unless the Quote has two options",
                )
            )
        else:
            violations.extend(
                validate_text(
                    text,
                    field=field,
                    available_placeholders=context.available_placeholders,
                    max_length=LENGTH_LIMITS[field],
                )
            )
    return tuple(violations)
