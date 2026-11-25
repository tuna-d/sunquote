"""GET /quotes/{id}/document: the printable Turkish quote.

Fixed inputs as in tests/api/test_quotes.py: the default 4.0 kWp Consumption-Matched system
costs 132,500 TRY before VAT and 159,000 TRY with it; Roof-Max gets a second option.
"""

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from sunquote.api import turkish
from sunquote.api.document import render_quote_document
from sunquote.api.narrative_text import fill_narrative
from sunquote.domain.narrative import NarrativeDraft
from sunquote.domain.ports import StoredQuote
from sunquote.domain.quote import build_quote
from tests.api.test_quotes import PROBLEM_JSON, valid_body, with_change
from tests.factories import (
    QUOTE_DATE,
    QUOTE_NUMBER,
    make_exchange_rate,
    make_financial_assumptions,
    make_reference_data,
    make_request,
    make_specific_yield,
)


def create(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post("/quotes", json=body or valid_body())
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def one_option_body() -> dict[str, Any]:
    # 20 m2 at coverage 0.80 fits exactly the 8 panels the consumption target asks for, so
    # Roof-Max gives the same panel count and the Quote keeps a single option.
    return with_change("roof.usable_area_m2", 20)


def document(client: TestClient, quote: dict[str, Any]) -> str:
    response = client.get(f"/quotes/{quote['id']}/document")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    return response.text


def places(value: Any, count: int) -> str:
    return turkish.format_decimal(Decimal(str(value)).quantize(Decimal(1).scaleb(-count)))


def test_a_two_option_quote_renders_as_html(client: TestClient) -> None:
    quote = create(client)
    assert len(quote["system_options"]) == 2

    page = document(client, quote)

    assert page.lstrip().lower().startswith("<!doctype html>")
    assert 'lang="tr"' in page
    assert page.count('class="option"') == 2


def test_a_one_option_quote_renders_with_a_single_option(client: TestClient) -> None:
    quote = create(client, one_option_body())
    assert len(quote["system_options"]) == 1

    page = document(client, quote)

    assert page.count('class="option"') == 1


def test_the_options_comparison_shows_only_with_two_options(client: TestClient) -> None:
    two = document(client, create(client))
    one = document(client, create(client, one_option_body()))

    assert 'data-slot="options_comparison"' in two
    assert 'data-slot="options_comparison"' not in one
    for slot in ("greeting", "summary", "next_steps"):
        assert f'data-slot="{slot}"' in two
        assert f'data-slot="{slot}"' in one


def test_the_header_shows_number_dates_customer_and_coordinates(client: TestClient) -> None:
    quote = create(client)

    page = document(client, quote)

    assert quote["quote_number"] in page
    assert "24.11.2026" in page  # quote date
    assert "09.12.2026" in page  # valid until, 15 days later
    assert "Şule Öztürk" in page
    assert "39,9334" in page
    assert "32,8597" in page  # no resolved Address yet


def test_the_header_shows_the_resolved_address_for_an_address_quote(client: TestClient) -> None:
    body = {**valid_body(), "site": {"address": "Ankara landmark"}}
    quote = create(client, body)

    page = document(client, quote)

    assert "An\u0131tkabir, Çankaya, Ankara, Türkiye" in page


def test_the_header_shows_coordinates_when_they_take_precedence(client: TestClient) -> None:
    quote = create(client, with_change("site.address", "Ankara landmark"))

    page = document(client, quote)

    assert "39,9334" in page
    assert "32,8597" in page


def test_user_supplied_text_is_escaped(client: TestClient) -> None:
    quote = create(client, with_change("customer.name", "<i>Ali</i>"))

    page = document(client, quote)

    assert "<i>Ali</i>" not in page
    assert escape("<i>Ali</i>") in page


def test_every_option_figure_matches_the_quote_displayed_values(client: TestClient) -> None:
    quote = create(client)
    page = document(client, quote)

    for option in quote["system_options"]:
        price = option["price"]
        savings = option["savings"]
        expected = [
            places(option["capacity_kwp"], 2),
            turkish.format_int(option["annual_production_kwh"]),
            str(option["panel_count"]),
            option["panel"]["model"],
            option["inverter"]["model"],
            turkish.format_try(price["sale_price_try"]),
            turkish.format_try(price["vat_try"]),
            turkish.format_try(price["total_try"]),
            turkish.format_try(savings["first_year_annual_savings_try"]),
            turkish.format_try(savings["lifetime_savings_try"]),
            places(savings["payback_period_years"], 1),
        ]
        for text in expected:
            assert text in page, text
        for month in option["monthly_production_kwh"]:
            assert turkish.format_int(month["production_kwh"]) in page


def test_the_monthly_production_has_a_table_and_css_bars_without_javascript(
    client: TestClient,
) -> None:
    page = document(client, create(client))

    assert "<table" in page
    assert 'class="bar"' in page
    for month in ("Ocak", "Haziran", "Aralık"):
        assert month in page
    assert "<script" not in page.lower()


def test_each_option_explains_its_strategy_and_binding_limit_in_turkish(
    client: TestClient,
) -> None:
    page = document(client, create(client))

    assert "Tüketime göre boyutlandırma" in page
    assert "Çatıya göre boyutlandırma" in page
    assert "Boyutu sınırlayan etken" in page


def test_the_assumptions_section_states_what_the_quote_was_calculated_with(
    client: TestClient,
) -> None:
    quote = create(client)
    assumptions = quote["assumptions"]
    tariff = assumptions["tariff"]
    rate = assumptions["exchange_rate"]

    page = document(client, quote)

    assert 'id="assumptions"' in page
    expected = [
        places(rate["rate"], 4),
        "23.11.2026",  # the Exchange Rate's date
        f"günlük {turkish.format_decimal(Decimal(str(tariff['tier_threshold_kwh_per_day'])))} kWh",
        turkish.format_try_per_kwh(Decimal(str(tariff["low_tariff_try_per_kwh"]))),
        turkish.format_try_per_kwh(Decimal(str(tariff["high_tariff_try_per_kwh"]))),
        turkish.format_try_per_kwh(Decimal(str(tariff["export_price_try_per_kwh"]))),
        "Aylık mahsuplaşma",
        "%2",  # real tariff escalation
        "%0,5",  # panel degradation (0.005 in the test Catalog)
        "15 gün",  # Validity Period
    ]
    for text in expected:
        assert text in page, text


def test_the_document_says_what_share_comes_off_the_bill_and_the_price_of_the_rest(
    client: TestClient,
) -> None:
    quote = create(client)
    export = turkish.format_try_per_kwh(
        Decimal(str(quote["assumptions"]["tariff"]["export_price_try_per_kwh"]))
    )

    page = document(client, quote)

    # 5,120 of 6,000 kWh (Consumption-Matched) and 5,980 of 12,000 kWh (Roof-Max), by month.
    assert "Faturadan düşen üretim" in page
    assert f"%85,3 (kalanı {export} fiyatıyla şebekeye satılır)" in page
    assert f"%49,8 (kalanı {export} fiyatıyla şebekeye satılır)" in page
    assert "Öz tüketim" not in page


def test_the_document_says_lifetime_figures_are_in_todays_lira(client: TestClient) -> None:
    page = document(client, create(client))

    assert "bugünkü lira" in page
    assert "reel" in page


def test_the_document_says_when_the_inverter_is_replaced_or_that_it_is_not_needed() -> None:
    def page_for(*, lifetime_years: int, replacement_year: int) -> str:
        quote = build_quote(
            request=make_request(),
            specific_yield=make_specific_yield(),
            reference_data=make_reference_data(
                financial=make_financial_assumptions(
                    lifetime_years=lifetime_years, replacement_year=replacement_year
                )
            ),
            exchange_rate=make_exchange_rate(),
            quote_date=QUOTE_DATE,
            quote_number=QUOTE_NUMBER,
        )
        stored = StoredQuote(id=uuid4(), created_at=datetime(2026, 11, 24, tzinfo=UTC), quote=quote)
        return render_quote_document(stored)

    replaced = page_for(lifetime_years=25, replacement_year=12)
    not_needed = page_for(lifetime_years=10, replacement_year=12)

    assert "İnverterin 12. yılda yenilenmesi hesaba katıldı." in replaced
    assert "inverter yenilemesi gerekmediği" not in replaced
    assert "Analiz süresi içinde inverter yenilemesi gerekmediği varsayıldı." in not_needed
    assert "yılda yenilenmesi" not in not_needed


def test_a_payback_beyond_the_lifetime_gets_its_own_sentence(client: TestClient) -> None:
    body = valid_body()
    body["exchange_rate_override"] = {"rate": 100000, "date": "2026-11-23"}
    quote = create(client, body)
    assert quote["system_options"][0]["savings"]["payback_beyond_lifetime"] is True

    page = document(client, quote)

    assert "geri ödenmiyor" in page
    assert "25 yıl" in page
    assert "None" not in page


def test_an_overridden_exchange_rate_is_labelled_as_such(client: TestClient) -> None:
    default = document(client, create(client))
    body = valid_body()
    body["exchange_rate_override"] = {"rate": 41, "date": "2026-11-23"}
    overridden = document(client, create(client, body))

    assert "TCMB" in default
    assert "Satış temsilcisi" in overridden


def test_the_page_has_print_css_for_a4(client: TestClient) -> None:
    page = document(client, create(client))

    assert "@page" in page
    assert "A4" in page
    assert "@media print" in page


def test_an_unknown_id_is_a_404_problem(client: TestClient) -> None:
    response = client.get(f"/quotes/{uuid4()}/document")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["type"] == "urn:sunquote:problem:quote-not-found"


def test_a_malformed_id_is_a_validation_problem(client: TestClient) -> None:
    response = client.get("/quotes/not-a-uuid/document")

    assert response.status_code == 422


def test_the_narrative_text_is_filled_from_placeholders_only() -> None:
    narrative = NarrativeDraft(
        greeting="Merhaba {customer_name}",
        summary="Sistem {option_1_capacity_kwp} kWp.",
        options_comparison="{option_1_total_try} ve {option_2_total_try}.",
        next_steps="Geçerlilik: {valid_until}.",
    )

    filled = fill_narrative(
        narrative,
        {
            "customer_name": "Ayşe",
            "option_1_capacity_kwp": "4,00",
            "option_1_total_try": "1 TL",
            "option_2_total_try": "2 TL",
            "valid_until": "09.12.2026",
        },
    )

    assert filled.greeting == "Merhaba Ayşe"
    assert filled.summary == "Sistem 4,00 kWp."
    assert filled.options_comparison == "1 TL ve 2 TL."
    assert filled.next_steps == "Geçerlilik: 09.12.2026."


def test_the_default_narrative_figures_come_from_the_quote(client: TestClient) -> None:
    quote = create(client)
    first = quote["system_options"][0]

    page = document(client, quote)

    summary = page.split('data-slot="summary"')[1].split("</")[0]
    assert places(first["capacity_kwp"], 2) in summary
    assert turkish.format_try(first["price"]["total_try"]) in summary
    assert "{" not in page.split("<body")[1]


def test_a_consumption_derived_from_a_monthly_bill_is_explained(client: TestClient) -> None:
    quote = create(client, with_change("consumption", {"monthly_bill_try": 2000}))
    annual = quote["assumptions"]["annual_consumption_kwh"]

    page = document(client, quote)

    assert "Aylık elektrik faturanız" in page
    assert turkish.format_int(round(annual)) in page
    assert "2.000 TL" in page
