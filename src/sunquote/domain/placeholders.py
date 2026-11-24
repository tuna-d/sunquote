"""The Narrative's placeholder vocabulary: a closed list, written once (ADR 0001).

The writer is told which placeholders it may use, the validator rejects any other, and the
renderer fills them from the Quote's displayed figures. All three read this module, so the
syntax and the list cannot drift apart.

Syntax: `{name}`. Options are addressed by position, `{option_1_capacity_kwp}`.
"""

import re
from collections.abc import Mapping, Sequence

# Matches a whole `{...}` group, whatever is inside, so malformed names are seen too.
PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]*)\}")

QUOTE_PLACEHOLDERS = ("customer_name", "quote_number", "valid_until", "validity_period_days")

PAYBACK_YEARS = "payback_years"
OPTION_PLACEHOLDERS = (
    "capacity_kwp",
    "panel_count",
    "panel_model",
    "inverter_model",
    "annual_production_kwh",
    "sale_price_try",
    "vat_try",
    "total_try",
    "first_year_savings_try",
    PAYBACK_YEARS,
    "lifetime_savings_try",
)

# A Quote holds one or two System Options.
MAX_OPTIONS = 2


def option_placeholder(number: int, name: str) -> str:
    """The placeholder of option `number` (1-based), for example `option_1_total_try`."""
    return f"option_{number}_{name}"


def known_placeholders() -> frozenset[str]:
    """Every placeholder in the vocabulary, whatever the Quote."""
    return frozenset(
        (
            *QUOTE_PLACEHOLDERS,
            *(
                option_placeholder(number, name)
                for number in range(1, MAX_OPTIONS + 1)
                for name in OPTION_PLACEHOLDERS
            ),
        )
    )


def available_placeholders(*, payback_beyond_lifetime: Sequence[bool]) -> frozenset[str]:
    """The placeholders a Quote can fill: one flag per System Option, true when that option's
    payback falls beyond the lifetime (it has no Payback Period to show)."""
    available = set(QUOTE_PLACEHOLDERS)
    for number, beyond_lifetime in enumerate(payback_beyond_lifetime, start=1):
        for name in OPTION_PLACEHOLDERS:
            if name == PAYBACK_YEARS and beyond_lifetime:
                continue
            available.add(option_placeholder(number, name))
    return frozenset(available)


def fill_placeholders(text: str, figures: Mapping[str, str]) -> str:
    """Replace every `{name}` with its figure in one pass; a name without a figure raises
    `KeyError`. A figure is inserted as is and never read for placeholders itself."""
    return PLACEHOLDER_PATTERN.sub(lambda match: figures[match.group(1)], text)
