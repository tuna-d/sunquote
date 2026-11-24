"""The Narrative as the Customer reads it: the prose slots with every placeholder filled.

The slots hold only text and `{placeholders}` from the closed list in
`sunquote.domain.placeholders` (ADR 0001). `placeholder_figures` fills that whole vocabulary
from the same formatted figures the quote document shows, so a writer can change the words
without touching a number. A Quote's stored Narrative is shown when its source is `llm`; else
the fixed Turkish text below, which belongs to this layer.

The JSON response and the printable document both read this module.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from sunquote.api import turkish
from sunquote.api.option_views import OptionView
from sunquote.domain.narrative import NarrativeDraft, NarrativeSource, has_comparison
from sunquote.domain.placeholders import (
    OPTION_PLACEHOLDERS,
    PAYBACK_YEARS,
    QUOTE_PLACEHOLDERS,
    available_placeholders,
    fill_placeholders,
    option_placeholder,
)
from sunquote.domain.ports import StoredQuote

FIXED_GREETING = "Sayın {customer_name},"
FIXED_SUMMARY = (
    "Çatınız ve elektrik tüketiminiz için hazırladığımız teklif aşağıdadır. İlk seçenek "
    "{option_1_capacity_kwp} kWp gücünde bir sistemdir; yılda yaklaşık "
    "{option_1_annual_production_kwh} kWh elektrik üretmesi ve KDV dahil "
    "{option_1_total_try} tutarında olması beklenmektedir."
)
FIXED_OPTIONS_COMPARISON = (
    "İki seçenek boyut ve fiyat bakımından farklıdır: ilk seçenek {option_1_capacity_kwp} kWp "
    "ve {option_1_total_try}, ikinci seçenek {option_2_capacity_kwp} kWp ve "
    "{option_2_total_try} tutarındadır (KDV dahil). Hangisinin size uygun olduğunu "
    "birlikte değerlendirebiliriz."
)
FIXED_NEXT_STEPS = (
    "Teklifteki fiyatlar {valid_until} tarihine kadar, yani {validity_period_days} gün "
    "geçerlidir. Teklifi onaylamak veya sorularınız için bizimle iletişime geçebilirsiniz."
)


@dataclass(frozen=True, slots=True)
class FilledNarrative:
    """The prose slots with every placeholder filled. `options_comparison` is None unless the
    Quote has two System Options."""

    greeting: str
    summary: str
    options_comparison: str | None
    next_steps: str


def fixed_draft(option_count: int) -> NarrativeDraft:
    """The template's fixed Turkish text, for a Quote with `option_count` System Options.

    It follows the same rules as a written draft: no digits, only available placeholders and a
    comparison only with two options.
    """
    return NarrativeDraft(
        greeting=FIXED_GREETING,
        summary=FIXED_SUMMARY,
        next_steps=FIXED_NEXT_STEPS,
        options_comparison=FIXED_OPTIONS_COMPARISON if has_comparison(option_count) else None,
    )


def fill_narrative(draft: NarrativeDraft, figures: Mapping[str, str]) -> FilledNarrative:
    """Replace every `{placeholder}` with its formatted figure. An unknown one raises KeyError."""
    comparison = draft.options_comparison
    return FilledNarrative(
        greeting=fill_placeholders(draft.greeting, figures),
        summary=fill_placeholders(draft.summary, figures),
        options_comparison=(
            fill_placeholders(comparison, figures) if comparison and comparison.strip() else None
        ),
        next_steps=fill_placeholders(draft.next_steps, figures),
    )


def _option_figures(option: OptionView) -> dict[str, str]:
    """The display value behind each name in `OPTION_PLACEHOLDERS`."""
    return {
        "capacity_kwp": option.capacity_kwp,
        "panel_count": option.panel_count,
        "panel_model": option.panel_model,
        "inverter_model": option.inverter_model,
        "annual_production_kwh": option.annual_production_kwh,
        "sale_price_try": option.sale_price,
        "vat_try": option.vat,
        "total_try": option.total,
        "first_year_savings_try": option.first_year_savings,
        PAYBACK_YEARS: option.payback,
        "lifetime_savings_try": option.lifetime_savings,
    }


def placeholder_figures(stored: StoredQuote, options: tuple[OptionView, ...]) -> dict[str, str]:
    """The display value of every placeholder the Quote can fill, and no other.

    The names come from `sunquote.domain.placeholders`, so a placeholder added there without a
    figure here raises `KeyError` instead of reaching the Customer as `{name}`. An option
    beyond its lifetime has no payback figure.
    """
    quote = stored.quote
    quote_figures = {
        "customer_name": quote.customer.name,
        "quote_number": quote.quote_number,
        "valid_until": turkish.format_date(quote.valid_until),
        "validity_period_days": turkish.format_int(quote.assumptions.pricing.validity_period_days),
    }
    available = available_placeholders(
        payback_beyond_lifetime=[option.payback_beyond_lifetime for option in options]
    )
    figures = {name: quote_figures[name] for name in QUOTE_PLACEHOLDERS}
    for option in options:
        option_figures = _option_figures(option)
        for name in OPTION_PLACEHOLDERS:
            placeholder = option_placeholder(option.number, name)
            if placeholder in available:
                figures[placeholder] = option_figures[name]
    return figures


def stored_narrative(stored: StoredQuote, options: tuple[OptionView, ...]) -> FilledNarrative:
    """The Narrative a stored Quote shows: its stored draft when the source is `llm`, else the
    fixed text, with every placeholder filled from the Quote. `options` are the Quote's option
    views (`option_views(stored)`)."""
    record = stored.quote.narrative
    draft = record.draft
    if record.source is not NarrativeSource.LLM or draft is None:
        draft = fixed_draft(len(stored.quote.system_options))
    return fill_narrative(draft, placeholder_figures(stored, options))
