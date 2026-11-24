import re

from sunquote.api.assistant_tools import MissingField, create_quote_request
from sunquote.domain.model import RoofType
from tests.eval.extraction import load_extraction_scenarios


def test_extraction_scenarios_cover_the_requested_language_and_follow_ups() -> None:
    scenarios = load_extraction_scenarios()
    assert len(scenarios) == len({scenario.name for scenario in scenarios}) == 20

    quote_cases = []
    missing_fields = []
    for scenario in scenarios:
        if scenario.arguments is not None:
            quote_cases.append((scenario.messages, create_quote_request(scenario.arguments)))
        else:
            assert scenario.missing_fields is not None
            missing_fields.append(set(scenario.missing_fields))

    assert len(missing_fields) >= 5
    assert {
        MissingField.ROOF_TILT,
        MissingField.CONSUMPTION,
        MissingField.CUSTOMER_NAME,
        MissingField.SITE_ADDRESS,
    } <= set.union(*missing_fields)
    assert any(len(fields) > 1 for fields in missing_fields)
    assert sum(len(messages) > 1 for messages, _ in quote_cases) >= 3

    assert {body.roof.roof_type for _, body in quote_cases} == {RoofType.FLAT, RoofType.PITCHED}
    assert any(
        re.search(r"\b(?:düz çatı|teras)", " ".join(messages).lower())
        for messages, body in quote_cases
        if body.roof.roof_type is RoofType.FLAT
    )
    for bearing, word in enumerate(
        ["kuzey", "kuzeydoğu", "doğu", "güneydoğu", "güney", "güneybatı", "batı", "kuzeybatı"]
    ):
        assert any(
            re.search(rf"\b{word}(?:[ae]|y[ae])?\b", " ".join(messages).lower())
            and "eğimli çatı" in " ".join(messages).lower()
            and body.roof.roof_type is RoofType.PITCHED
            and body.roof.azimuth_deg == bearing * 45
            for messages, body in quote_cases
        ), word

    assert any(
        "bin beş yüz lira" in " ".join(messages).lower()
        and body.consumption.monthly_bill_try == 1500
        for messages, body in quote_cases
    )
    assert any(
        "40 metrekare kadar" in " ".join(messages).lower() and body.roof.usable_area_m2 == 40
        for messages, body in quote_cases
    )
    assert any(
        re.search(r"\d+ kwh\b.*\d+ tl\b", " ".join(messages).lower())
        and body.consumption.monthly_consumption_kwh is not None
        and body.consumption.monthly_bill_try is None
        for messages, body in quote_cases
    )
