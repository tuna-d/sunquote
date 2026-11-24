"""Load and grade Turkish extraction scenarios without calling Gemini."""

import tomllib
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from sunquote.domain.conversation import MissingField


class ExtractionScenario(BaseModel):
    name: str
    messages: list[str] = Field(min_length=1)
    arguments: dict[str, object] | None = None
    missing_fields: list[MissingField] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_one_outcome(self) -> Self:
        if (self.arguments is None) == (self.missing_fields is None):
            raise ValueError("specify exactly one of arguments and missing_fields")
        return self


def load_extraction_scenarios() -> list[ExtractionScenario]:
    with Path(__file__).with_name("extraction_scenarios.toml").open("rb") as file:
        return [ExtractionScenario.model_validate(item) for item in tomllib.load(file)["scenario"]]


def _leaf_paths(arguments: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    fields = {}
    for name, value in arguments.items():
        path = f"{prefix}{name}"
        if isinstance(value, Mapping) and value:
            fields.update(_leaf_paths(value, f"{path}."))
        else:
            fields[path] = value
    return fields


def _address(value: str) -> str:
    return " ".join(value.translate(str.maketrans("İI", "iı")).lower().split())


def _matches(path: str, expected: object, actual: object) -> bool:
    if isinstance(expected, str):
        if not isinstance(actual, str):
            return False
        if path == "site.address":
            return _address(expected) == _address(actual)
        return expected == actual

    if isinstance(expected, int | float | Decimal):
        # The tool accepts numbers as JSON numbers or decimal strings.
        if isinstance(actual, bool) or not isinstance(actual, int | float | Decimal | str):
            return False
        try:
            number = Decimal(str(actual))
        except InvalidOperation:
            return False
        target = Decimal(str(expected))
        tolerance = max(abs(target) * Decimal("0.01"), Decimal("0.5"))
        return number.is_finite() and abs(number - target) <= tolerance

    return expected == actual


def grade_extraction(
    calls: Sequence[Mapping[str, object]],
    missing_fields: Sequence[str],
    *,
    expected_arguments: Mapping[str, object] | None = None,
    expected_missing_fields: Sequence[MissingField] = (),
) -> dict[str, bool]:
    if expected_arguments is None:
        return {
            "create_quote": not calls,
            "missing_fields": set(missing_fields) == set(expected_missing_fields),
        }

    expected = _leaf_paths(expected_arguments)
    actual = _leaf_paths(calls[0]) if calls else {}
    grades = {"create_quote": len(calls) == 1}
    for path in sorted(expected.keys() | actual.keys()):
        grades[path] = (
            path in expected and path in actual and _matches(path, expected[path], actual[path])
        )
    return grades
