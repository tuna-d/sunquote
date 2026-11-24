from sunquote.domain.model import RoofType
from sunquote.domain.narrative_context import build_narrative_context
from sunquote.domain.sizing import BindingLimit
from tests.eval.scenarios import SCENARIOS


def test_narrative_scenarios_cover_quote_outcomes() -> None:
    quotes = [scenario.build() for scenario in SCENARIOS]
    options = [option for quote in quotes for option in quote.system_options]

    assert {len(quote.system_options) for quote in quotes} == {1, 2}
    assert {quote.assumptions.roof_type for quote in quotes} == {RoofType.PITCHED, RoofType.FLAT}
    assert {option.binding_limit for option in options} == set(BindingLimit)
    assert {option.savings.payback_beyond_lifetime for option in options} == {False, True}
    assert {quote.assumptions.consumption_derived_from_bill for quote in quotes} == {False, True}

    assumptions = [quote.assumptions for quote in quotes]
    assert any(a.annual_consumption_kwh < a.tariff.tier_threshold_kwh_per_year for a in assumptions)
    assert any(a.annual_consumption_kwh > a.tariff.tier_threshold_kwh_per_year for a in assumptions)
    assert len(quotes) == len({quote.quote_number for quote in quotes}) == 20
    assert len({scenario.name for scenario in SCENARIOS}) == len(quotes)
    assert len({build_narrative_context(quote) for quote in quotes}) == len(quotes)
