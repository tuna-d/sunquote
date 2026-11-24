"""The Narrative's pure parts: the placeholder vocabulary, the anonymised context built from a
Quote, and the validator that enforces ADR 0001 on a draft."""

from dataclasses import fields, is_dataclass, replace
from decimal import Decimal
from typing import Any

import pytest

from sunquote.domain.model import RoofType
from sunquote.domain.narrative import (
    NarrativeContext,
    NarrativeDraft,
    NarrativeRecord,
    NarrativeSource,
    Orientation,
    ViolationKind,
    validate_narrative,
)
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.placeholders import available_placeholders, fill_placeholders
from sunquote.domain.quote import Quote, build_quote
from sunquote.domain.sizing import BindingLimit, SizingStrategy
from tests.factories import (
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_exchange_rate,
    make_reference_data,
    make_request,
    make_specific_yield,
    make_tariff,
)

OPTION_FIELDS = (
    "capacity_kwp",
    "panel_count",
    "panel_model",
    "inverter_model",
    "annual_production_kwh",
    "sale_price_try",
    "vat_try",
    "total_try",
    "first_year_savings_try",
    "payback_years",
    "lifetime_savings_try",
)
QUOTE_LEVEL = ("customer_name", "quote_number", "valid_until", "validity_period_days")


def build(
    *,
    usable_area_m2: str = "40",
    monthly_consumption_kwh: str = "500",
    azimuth_deg: str = "180",
    roof_type: RoofType = RoofType.PITCHED,
    threshold_kwh_per_year: str = "3000",
) -> Quote:
    return build_quote(
        request=make_request(
            usable_area_m2=usable_area_m2,
            monthly_consumption_kwh=monthly_consumption_kwh,
            azimuth_deg=azimuth_deg,
            roof_type=roof_type,
        ),
        specific_yield=make_specific_yield(),
        reference_data=make_reference_data(
            tariff=make_tariff(threshold_kwh_per_year=threshold_kwh_per_year)
        ),
        exchange_rate=make_exchange_rate(),
        quote_date=QUOTE_DATE,
        quote_number=QUOTE_NUMBER,
    )


def two_options() -> Quote:
    quote = build()
    assert len(quote.system_options) == 2
    return quote


def one_option() -> Quote:
    # 20 m2 fits exactly the 8 panels the consumption target asks for.
    quote = build(usable_area_m2="20")
    assert len(quote.system_options) == 1
    return quote


def with_savings(
    quote: Quote, number: int, *, payback_years: str | None, beyond_lifetime: bool = False
) -> Quote:
    options = list(quote.system_options)
    option = options[number - 1]
    options[number - 1] = replace(
        option,
        savings=replace(
            option.savings,
            payback_years=None if payback_years is None else Decimal(payback_years),
            payback_beyond_lifetime=beyond_lifetime,
        ),
    )
    return replace(quote, system_options=tuple(options))


# --- Placeholder vocabulary -----------------------------------------------------------------


def test_two_options_make_every_quote_and_option_placeholder_available() -> None:
    expected = {
        *QUOTE_LEVEL,
        *(f"option_{n}_{name}" for n in (1, 2) for name in OPTION_FIELDS),
    }

    assert available_placeholders(payback_beyond_lifetime=(False, False)) == expected


def test_a_single_option_has_no_option_2_placeholders() -> None:
    available = available_placeholders(payback_beyond_lifetime=(False,))

    assert not any(name.startswith("option_2_") for name in available)
    assert "option_1_capacity_kwp" in available


def test_an_option_beyond_its_lifetime_has_no_payback_placeholder() -> None:
    available = available_placeholders(payback_beyond_lifetime=(False, True))

    assert "option_1_payback_years" in available
    assert "option_2_payback_years" not in available
    assert "option_2_total_try" in available


def test_placeholders_are_filled_from_the_figures_and_unknown_ones_raise() -> None:
    figures = {"customer_name": "Ayşe", "valid_until": "09.12.2026"}

    assert fill_placeholders("Sayın {customer_name}, {valid_until}", figures) == (
        "Sayın Ayşe, 09.12.2026"
    )
    with pytest.raises(KeyError):
        fill_placeholders("{option_3_total_try}", figures)


def test_a_filled_figure_that_looks_like_a_placeholder_is_not_filled_again() -> None:
    assert fill_placeholders("{customer_name}", {"customer_name": "{quote_number}"}) == (
        "{quote_number}"
    )


# --- Narrative context ----------------------------------------------------------------------


def test_the_context_carries_each_options_strategy_and_binding_limit() -> None:
    context = build_narrative_context(two_options())

    assert context.option_count == 2
    assert [option.sizing_strategy for option in context.options] == [
        SizingStrategy.CONSUMPTION_MATCHED,
        SizingStrategy.ROOF_MAX,
    ]
    assert [option.binding_limit for option in context.options] == [
        BindingLimit.CONSUMPTION_TARGET,
        BindingLimit.ROOF,
    ]


@pytest.mark.parametrize(
    ("azimuth_deg", "word"),
    [
        ("0", Orientation.NORTH),
        ("22.4", Orientation.NORTH),
        ("22.5", Orientation.NORTH_EAST),
        ("90", Orientation.EAST),
        ("135", Orientation.SOUTH_EAST),
        ("180", Orientation.SOUTH),
        ("225", Orientation.SOUTH_WEST),
        ("270", Orientation.WEST),
        ("315", Orientation.NORTH_WEST),
        ("337.4", Orientation.NORTH_WEST),
        ("337.5", Orientation.NORTH),
        ("359", Orientation.NORTH),
    ],
)
def test_a_pitched_roofs_orientation_is_an_eight_point_compass_word(
    azimuth_deg: str, word: Orientation
) -> None:
    context = build_narrative_context(build(azimuth_deg=azimuth_deg))

    assert context.roof_type is RoofType.PITCHED
    assert context.orientation is word


def test_a_flat_roof_is_flat_whatever_azimuth_was_given() -> None:
    context = build_narrative_context(build(roof_type=RoofType.FLAT, azimuth_deg="90"))

    assert context.roof_type is RoofType.FLAT
    assert context.orientation is Orientation.FLAT


@pytest.mark.parametrize(
    ("threshold_kwh_per_year", "above"),
    [("5999", True), ("6000", False), ("6001", False)],
)
def test_the_context_says_whether_consumption_is_above_the_tier_threshold(
    threshold_kwh_per_year: str, above: bool
) -> None:
    # 500 kWh a month is 6,000 kWh a year; consumption up to the threshold is all low tier.
    quote = build(monthly_consumption_kwh="500", threshold_kwh_per_year=threshold_kwh_per_year)

    assert build_narrative_context(quote).annual_consumption_above_tier_threshold is above


def test_with_two_options_the_context_compares_production_price_and_payback() -> None:
    quote = with_savings(with_savings(two_options(), 1, payback_years="5"), 2, payback_years="7")

    comparison = build_narrative_context(quote).comparison

    assert comparison is not None
    assert comparison.second_option_produces_more is True
    assert comparison.second_option_costs_more is True
    assert comparison.second_option_pays_back_sooner is False


def test_the_second_option_pays_back_sooner_when_its_payback_is_shorter() -> None:
    quote = with_savings(with_savings(two_options(), 1, payback_years="7"), 2, payback_years="5")

    comparison = build_narrative_context(quote).comparison

    assert comparison is not None
    assert comparison.second_option_pays_back_sooner is True


@pytest.mark.parametrize(
    ("first_beyond", "second_beyond", "sooner"),
    [(True, False, True), (False, True, False), (True, True, False)],
)
def test_a_payback_beyond_the_lifetime_counts_as_longer_than_any_payback(
    first_beyond: bool, second_beyond: bool, sooner: bool
) -> None:
    quote = two_options()
    for number, beyond in ((1, first_beyond), (2, second_beyond)):
        quote = with_savings(
            quote, number, payback_years=None if beyond else "9", beyond_lifetime=beyond
        )

    comparison = build_narrative_context(quote).comparison

    assert comparison is not None
    assert comparison.second_option_pays_back_sooner is sooner


def test_the_second_option_produces_and_costs_less_when_it_is_the_smaller_one() -> None:
    quote = two_options()
    first, second = quote.system_options
    swapped = replace(quote, system_options=(second, first))

    comparison = build_narrative_context(swapped).comparison

    assert comparison is not None
    assert comparison.second_option_produces_more is False
    assert comparison.second_option_costs_more is False


def test_a_single_option_has_no_comparison() -> None:
    assert build_narrative_context(one_option()).comparison is None


def test_the_context_flags_each_options_payback_beyond_the_lifetime() -> None:
    quote = with_savings(two_options(), 2, payback_years=None, beyond_lifetime=True)

    context = build_narrative_context(quote)

    assert [option.payback_beyond_lifetime for option in context.options] == [False, True]


def test_the_context_lists_the_placeholders_available_for_the_quote() -> None:
    quote = with_savings(two_options(), 2, payback_years=None, beyond_lifetime=True)

    context = build_narrative_context(quote)

    assert set(context.available_placeholders) == available_placeholders(
        payback_beyond_lifetime=(False, True)
    )
    assert list(context.available_placeholders) == sorted(context.available_placeholders)
    one = build_narrative_context(one_option())
    assert not any(name.startswith("option_2_") for name in one.available_placeholders)


def _field_names(cls: type) -> set[str]:
    names: set[str] = set()
    for field in fields(cls):
        names.add(field.name)
        for candidate in _nested_dataclasses(field.type):
            names |= _field_names(candidate)
    return names


def _nested_dataclasses(annotation: Any) -> list[type]:
    found = [annotation] if isinstance(annotation, type) and is_dataclass(annotation) else []
    for argument in getattr(annotation, "__args__", ()):
        found += _nested_dataclasses(argument)
    return found


def test_the_context_type_has_no_field_for_personal_data() -> None:
    names = _field_names(NarrativeContext)

    personal = {"customer", "name", "address", "coordinates", "latitude", "longitude"}
    personal |= {"phone", "email", "geocoding_result", "display_name"}
    assert names & personal == set()
    assert "options" in names  # the walk reached the nested types


# --- Validator ------------------------------------------------------------------------------


def valid_draft(context: NarrativeContext) -> NarrativeDraft:
    return NarrativeDraft(
        greeting="Sayın {customer_name},",
        summary="Önerilen sistem {option_1_capacity_kwp} kWp gücündedir.",
        next_steps="Fiyatlar {valid_until} tarihine kadar geçerlidir.",
        options_comparison=(
            "{option_1_total_try} ile {option_2_total_try} arasındaki farkı birlikte görelim."
            if context.option_count == 2
            else None
        ),
    )


def test_a_valid_draft_has_no_violations() -> None:
    for quote in (two_options(), one_option()):
        context = build_narrative_context(quote)

        assert validate_narrative(valid_draft(context), context) == ()


@pytest.mark.parametrize("field", ["greeting", "summary", "next_steps", "options_comparison"])
@pytest.mark.parametrize(
    "text",
    [
        "Yaklaşık 8,4 kWp",
        "8",
        "bir 5 yıl",
        "{option_1_capacity_kwp} kWp, yani 8,4 kWp",
        "Ankara'da 2 gün",
        "٣ gün",  # an Arabic-Indic digit is a digit too
    ],
)
def test_a_digit_outside_a_placeholder_is_a_violation(field: str, text: str) -> None:
    context = build_narrative_context(two_options())
    draft = replace(valid_draft(context), **{field: text})

    violations = validate_narrative(draft, context)

    assert [(v.kind, v.field) for v in violations] == [
        (ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER, field)
    ]


def test_digits_inside_placeholder_names_are_not_digits_outside_them() -> None:
    context = build_narrative_context(two_options())
    draft = replace(valid_draft(context), summary="{option_1_payback_years} {option_2_total_try}")

    assert validate_narrative(draft, context) == ()


@pytest.mark.parametrize(
    "text",
    [
        "{customer}",
        "{option_3_total_try}",
        "{option_1_price}",
        "{}",
        "{ customer_name }",
        "{customer_name!r}",
        "{customer_name:>10}",
        "{customer_name",
        "customer_name}",
    ],
)
def test_an_unknown_or_malformed_placeholder_is_a_violation(text: str) -> None:
    context = build_narrative_context(two_options())
    draft = replace(valid_draft(context), summary=text)

    violations = validate_narrative(draft, context)

    assert [(v.kind, v.field) for v in violations] == [
        (ViolationKind.UNKNOWN_PLACEHOLDER, "summary")
    ]


def test_a_known_placeholder_the_quote_does_not_offer_is_a_violation() -> None:
    one = build_narrative_context(one_option())
    beyond = build_narrative_context(
        with_savings(two_options(), 2, payback_years=None, beyond_lifetime=True)
    )

    for context, text in (
        (one, "{option_2_capacity_kwp}"),
        (beyond, "{option_2_payback_years}"),
    ):
        draft = replace(valid_draft(context), summary=text)

        violations = validate_narrative(draft, context)

        assert [(v.kind, v.field) for v in violations] == [
            (ViolationKind.UNAVAILABLE_PLACEHOLDER, "summary")
        ]
        assert text.strip("{}") in violations[0].detail


@pytest.mark.parametrize("field", ["greeting", "summary", "next_steps"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_a_blank_required_field_is_a_violation(field: str, blank: str) -> None:
    context = build_narrative_context(two_options())
    draft = replace(valid_draft(context), **{field: blank})

    assert [(v.kind, v.field) for v in validate_narrative(draft, context)] == [
        (ViolationKind.MISSING_FIELD, field)
    ]


def test_a_comparison_with_one_option_is_a_violation() -> None:
    context = build_narrative_context(one_option())
    draft = replace(valid_draft(context), options_comparison="{option_1_total_try}")

    assert [(v.kind, v.field) for v in validate_narrative(draft, context)] == [
        (ViolationKind.UNEXPECTED_COMPARISON, "options_comparison")
    ]


@pytest.mark.parametrize("comparison", [None, "", "  "])
def test_a_missing_comparison_with_two_options_is_a_violation(comparison: str | None) -> None:
    context = build_narrative_context(two_options())
    draft = replace(valid_draft(context), options_comparison=comparison)

    assert [(v.kind, v.field) for v in validate_narrative(draft, context)] == [
        (ViolationKind.MISSING_FIELD, "options_comparison")
    ]


@pytest.mark.parametrize("comparison", [None, ""])
def test_no_comparison_with_one_option_is_fine(comparison: str | None) -> None:
    context = build_narrative_context(one_option())
    draft = replace(valid_draft(context), options_comparison=comparison)

    assert validate_narrative(draft, context) == ()


@pytest.mark.parametrize(
    ("field", "limit"),
    [("greeting", 200), ("summary", 1200), ("options_comparison", 1200), ("next_steps", 800)],
)
def test_a_field_over_its_length_limit_is_a_violation(field: str, limit: int) -> None:
    context = build_narrative_context(two_options())
    at_limit = replace(valid_draft(context), **{field: "a" * limit})
    over_limit = replace(valid_draft(context), **{field: "a" * (limit + 1)})

    assert validate_narrative(at_limit, context) == ()
    assert [(v.kind, v.field) for v in validate_narrative(over_limit, context)] == [
        (ViolationKind.TOO_LONG, field)
    ]


def test_every_broken_rule_is_reported() -> None:
    context = build_narrative_context(two_options())
    draft = NarrativeDraft(
        greeting="",
        summary="8,4 kWp {nope}",
        next_steps="x" * 801,
        options_comparison=None,
    )

    violations = validate_narrative(draft, context)

    assert sorted((v.kind, v.field) for v in violations) == sorted(
        [
            (ViolationKind.MISSING_FIELD, "greeting"),
            (ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER, "summary"),
            (ViolationKind.UNKNOWN_PLACEHOLDER, "summary"),
            (ViolationKind.TOO_LONG, "next_steps"),
            (ViolationKind.MISSING_FIELD, "options_comparison"),
        ]
    )


# --- Narrative record -----------------------------------------------------------------------


def test_an_llm_record_needs_a_draft_and_a_model_and_a_fallback_has_neither() -> None:
    draft = NarrativeDraft(greeting="a", summary="b", next_steps="c")

    with pytest.raises(ValueError, match="llm"):
        NarrativeRecord(source=NarrativeSource.LLM, draft=None, model="m", generated_at=None)
    with pytest.raises(ValueError, match="llm"):
        NarrativeRecord(source=NarrativeSource.LLM, draft=draft, model=None, generated_at=None)
    with pytest.raises(ValueError, match="fallback"):
        NarrativeRecord(source=NarrativeSource.FALLBACK, draft=draft, model=None, generated_at=None)
    with pytest.raises(ValueError, match="fallback"):
        NarrativeRecord(source=NarrativeSource.FALLBACK, draft=None, model="m", generated_at=None)
