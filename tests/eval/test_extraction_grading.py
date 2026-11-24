import pytest

from sunquote.domain.conversation import MissingField, ToolCall
from tests.eval.extraction import grade_extraction


def test_exact_quote_arguments_pass() -> None:
    expected = {"customer": {"name": "Ada Örnek"}, "roof": {"roof_type": "flat"}}
    call = ToolCall("create_quote", expected)

    assert grade_extraction([call.arguments], (), expected_arguments=expected) == {
        "create_quote": True,
        "customer.name": True,
        "roof.roof_type": True,
    }


@pytest.mark.parametrize(
    ("target", "actual", "passes"),
    [
        (1500, "1485", True),
        (1500, 1515.01, False),
        (40, 39.5, True),
        (40, 40.51, False),
        (0, False, False),
        (40, "NaN", False),
        (40, "forty", False),
    ],
)
def test_numeric_tolerance(target: int, actual: object, passes: bool) -> None:
    call = ToolCall("create_quote", {"roof": {"usable_area_m2": actual}})
    grades = grade_extraction(
        [call.arguments], (), expected_arguments={"roof": {"usable_area_m2": target}}
    )

    assert grades["roof.usable_area_m2"] is passes


def test_only_address_gets_normalised_and_optional_fields_must_be_absent() -> None:
    expected = {
        "site": {"address": "Işık İstanbul"},
        "customer": {"name": "Ada Örnek"},
        "roof": {"roof_type": "flat"},
    }
    call = ToolCall(
        "create_quote",
        {
            "site": {"address": "  ışık\t istanbul\n"},
            "customer": {"name": "ada örnek", "email": None},
            "roof": {"roof_type": "Flat"},
        },
    )

    assert grade_extraction([call.arguments], (), expected_arguments=expected) == {
        "create_quote": True,
        "site.address": True,
        "customer.name": False,
        "customer.email": False,
        "roof.roof_type": False,
    }


def test_question_requires_exact_set_and_no_create_attempt() -> None:
    missing = [MissingField.ROOF_TILT, MissingField.CONSUMPTION]
    invalid_call = ToolCall("create_quote", {})

    assert grade_extraction([], missing[::-1], expected_missing_fields=missing) == {
        "create_quote": True,
        "missing_fields": True,
    }
    assert grade_extraction(
        [invalid_call.arguments], missing[:1], expected_missing_fields=missing
    ) == {
        "create_quote": False,
        "missing_fields": False,
    }
    assert not grade_extraction(
        [], [*missing, MissingField.SITE_ADDRESS], expected_missing_fields=missing
    )["missing_fields"]
