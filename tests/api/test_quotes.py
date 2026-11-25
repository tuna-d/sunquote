"""POST /quotes through the real FastAPI app with a fake Specific Yield provider.

Fixed inputs (see tests/factories.py): panel 0.5 kWp / 2.0 m2 at USD 100, coverage ratio 0.80,
specific yield 1,500 kWh/kWp, 40 TRY/USD unless a test says otherwise. The default 4.0 kWp
system gets the 3.5 kW inverter and costs 106,000 TRY (Sale Price 132,500, VAT 26,500).
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sunquote.domain.catalog import Catalog
from sunquote.domain.errors import LocationNotSupportedError, UpstreamUnavailableError
from sunquote.domain.money import Currency
from tests.conftest import ClientFactory
from tests.factories import (
    DEFAULT_INVERTERS,
    MONTHLY_YIELD_KWH_PER_KWP,
    QUOTE_DATE,
    make_exchange_rate,
    make_panel,
    make_reference_data,
    make_specific_yield,
)
from tests.fakes import (
    FakeExchangeRateProvider,
    FakeQuoteRepository,
    FakeSpecificYieldProvider,
    FixedClock,
)

PROBLEM_JSON = "application/problem+json"


def valid_body() -> dict[str, Any]:
    return {
        "customer": {
            "name": "Şule Öztürk",
            "phone": "+90 555 000 00 00",
            "email": "sule@example.com",
        },
        "site": {"latitude": 39.9334, "longitude": 32.8597},
        "roof": {
            "roof_type": "pitched",
            "usable_area_m2": 40,
            "azimuth_deg": 180,
            "tilt_deg": 30,
        },
        "consumption": {"monthly_consumption_kwh": 500},
        "subscriber_group": "residential",
    }


def with_change(path: str, value: Any) -> dict[str, Any]:
    """The valid body with one nested field replaced; a `value` of `...` deletes the field."""
    body = valid_body()
    *parents, leaf = path.split(".")
    target = body
    for key in parents:
        target = target[key]
    if value is ...:
        del target[leaf]
    else:
        target[leaf] = value
    return body


def test_creates_the_same_system_options_from_a_bill_as_from_kwh(client: TestClient) -> None:
    # Test tariff: 500 kWh a month is above every monthly threshold, so the bill is
    # (12 x 2,500 - 2 x 2,920) / 12 = 2,013.33... TRY (the digits a decimal string can hold).
    bill = "2013.333333333333333333333333333"
    response = client.post("/quotes", json=with_change("consumption", {"monthly_bill_try": bill}))
    direct = client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    assert quote["system_options"] == direct.json()["system_options"]
    assumptions = quote["assumptions"]
    assert assumptions["consumption_derived_from_bill"] is True
    assert Decimal(assumptions["derived_monthly_consumption_kwh"]) == pytest.approx(
        Decimal(500), abs=Decimal("1e-20")
    )
    assert assumptions["annual_consumption_kwh"] == 6000
    assert assumptions["submitted_request"]["consumption"] == {
        "monthly_consumption_kwh": None,
        "monthly_bill_try": bill,
    }


def test_direct_consumption_takes_precedence_over_a_monthly_bill(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("consumption.monthly_bill_try", 1125))
    direct = client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    assert quote["system_options"] == direct.json()["system_options"]
    assumptions = quote["assumptions"]
    assert assumptions["consumption_derived_from_bill"] is False
    assert assumptions["derived_monthly_consumption_kwh"] is None
    assert assumptions["annual_consumption_kwh"] == 6000
    assert assumptions["submitted_request"]["consumption"]["monthly_bill_try"] == "1125"


def test_creates_a_quote_with_a_consumption_matched_and_a_roof_max_option(
    client: TestClient,
) -> None:
    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 201
    quote = response.json()
    assert quote["customer"] == {
        "name": "Şule Öztürk",
        "phone": "+90 555 000 00 00",
        "email": "sule@example.com",
    }
    assert quote["quote_date"] == "2026-11-24"
    consumption_matched, roof_max = quote["system_options"]
    assert roof_max["strategy"] == "roof_max"
    assert roof_max["panel_count"] == 16
    assert roof_max["capacity_kwp"] == 8.0
    assert roof_max["binding_limit"] == "roof"
    assert roof_max["inverter"]["inverter_id"] == "i8"
    assert roof_max["annual_production_kwh"] == 12000
    assert roof_max["price"]["total_try"] == 276000
    option = consumption_matched
    assert option["strategy"] == "consumption_matched"
    assert option["panel_count"] == 8
    assert option["capacity_kwp"] == 4.0
    assert option["binding_limit"] == "consumption_target"
    assert option["panel"] == {
        "panel_id": "test-panel-500w",
        "manufacturer": "Test",
        "model": "T-500",
        "power_w": 500,
    }
    assert option["annual_production_kwh"] == 6000
    assert [m["month"] for m in option["monthly_production_kwh"]] == list(range(1, 13))
    assert [m["production_kwh"] for m in option["monthly_production_kwh"]] == [
        280, 360, 480, 560, 640, 700, 740, 680, 560, 440, 320, 240,
    ]  # fmt: skip


def test_a_given_contracted_power_caps_both_options_and_is_recorded_as_given(
    client: TestClient,
) -> None:
    body = {**valid_body(), "contracted_power_kw": 6}

    response = client.post("/quotes", json=body)

    assert response.status_code == 201
    quote = response.json()
    # Cap floor(6 x 1.30 / 0.5) = 15 panels: the target of 8 stays, the roof's 16 is cut to 15.
    consumption_matched, roof_max = quote["system_options"]
    assert (consumption_matched["panel_count"], consumption_matched["binding_limit"]) == (
        8,
        "consumption_target",
    )
    assert (roof_max["panel_count"], roof_max["binding_limit"]) == (15, "contracted_power")
    assert roof_max["inverter"]["ac_power_kw"] <= 6
    assert quote["assumptions"]["contracted_power"] == {"kw": 6, "source": "given"}
    assert quote["assumptions"]["submitted_request"]["contracted_power_kw"] == 6


def test_an_absent_contracted_power_uses_the_default_and_is_recorded_as_defaulted(
    client: TestClient,
) -> None:
    quote = client.post("/quotes", json=valid_body()).json()

    assert quote["assumptions"]["contracted_power"] == {"kw": 10, "source": "defaulted"}
    assert quote["assumptions"]["submitted_request"]["contracted_power_kw"] is None
    assert quote["assumptions"]["dc_ac_ratio_range"]["maximum"] == "1.30"


def test_a_null_contracted_power_counts_as_absent(client: TestClient) -> None:
    quote = client.post("/quotes", json={**valid_body(), "contracted_power_kw": None}).json()

    assert quote["assumptions"]["contracted_power"]["source"] == "defaulted"


def test_the_quote_collapses_to_one_option_when_the_cap_equalises_both(
    client: TestClient,
) -> None:
    body = {**valid_body(), "contracted_power_kw": 3}
    body["consumption"] = {"monthly_consumption_kwh": 2000}

    [option] = client.post("/quotes", json=body).json()["system_options"]

    assert option["strategy"] == "consumption_matched"
    assert (option["panel_count"], option["binding_limit"]) == (7, "contracted_power")


def test_a_contracted_power_too_small_for_a_panel_is_a_no_viable_system_problem(
    client: TestClient,
) -> None:
    response = client.post("/quotes", json={**valid_body(), "contracted_power_kw": 0.3})

    assert response.status_code == 422
    assert response.json()["type"] == "urn:sunquote:problem:no-viable-system"


def test_displayed_figures_are_rounded_by_the_policy(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    monthly = (Decimal("69.17"), *MONTHLY_YIELD_KWH_PER_KWP[1:])
    specific_yield_provider.specific_yield = make_specific_yield(annual="1472.13", monthly=monthly)

    option = client.post("/quotes", json=valid_body()).json()["system_options"][0]

    # 6000 kWh / 1472.13 kWh/kWp = 4.07 kWp -> 8 panels = 4 kWp. 4 x 1472.13 = 5888.52 kWh.
    assert option["capacity_kwp"] == 4.0
    assert option["annual_production_kwh"] == 5889
    # 4 x 69.17 = 276.68 kWh
    assert option["monthly_production_kwh"][0]["production_kwh"] == 277


def test_assumptions_record_the_submitted_input_pvgis_inputs_ratio_and_panel(
    client: TestClient,
) -> None:
    quote = client.post("/quotes", json=valid_body()).json()

    assumptions = quote["assumptions"]
    assert assumptions["submitted_request"] == {**valid_body(), "contracted_power_kw": None}
    assert assumptions["pvgis_inputs"] == {
        "source": "test",
        "latitude": 39.93,
        "longitude": 32.86,
        "tilt_deg": 30,
        "aspect_deg": 0,
        "system_loss_percent": 14,
    }
    assert assumptions["roof_type"] == "pitched"
    assert assumptions["effective_azimuth_deg"] == 180
    assert assumptions["effective_tilt_deg"] == 30
    assert assumptions["coverage_ratio"] == "0.80"
    assert assumptions["default_panel"] == {
        "panel_id": "test-panel-500w",
        "manufacturer": "Test",
        "model": "T-500",
        "power_w": 500,
        "length_mm": 2000,
        "width_mm": 1000,
        "area_m2": 2.0,
        "degradation_rate_per_year": "0.005",
        "unit_price": {"amount": "100", "currency": "USD"},
    }


def test_each_option_shows_the_inverter_and_the_price_in_whole_lira(client: TestClient) -> None:
    option = client.post("/quotes", json=valid_body()).json()["system_options"][0]

    assert option["inverter"] == {
        "inverter_id": "i35",
        "manufacturer": "Test",
        "model": "I35",
        "ac_power_kw": 3.5,
    }
    assert option["price"] == {
        "installation_cost_try": 106000,
        "sale_price_try": 132500,
        "vat_try": 26500,
        "total_try": 159000,
    }


def test_prices_are_rounded_half_up_but_the_assumptions_keep_full_precision(
    client: TestClient, exchange_rate_provider: FakeExchangeRateProvider
) -> None:
    exchange_rate_provider.rate = make_exchange_rate("41.2345")

    quote = client.post("/quotes", json=valid_body()).json()

    # Installation Cost 108,283.825; Sale Price 135,354.78125; VAT 27,070.95625; total 162,425.7375
    assert quote["system_options"][0]["price"] == {
        "installation_cost_try": 108284,
        "sale_price_try": 135355,
        "vat_try": 27071,
        "total_try": 162426,
    }
    assert quote["assumptions"]["exchange_rate"]["rate"] == "41.2345"
    assert quote["assumptions"]["pricing"]["margin"] == "0.25"


def test_assumptions_record_the_exchange_rate_and_every_unit_price(client: TestClient) -> None:
    assumptions = client.post("/quotes", json=valid_body()).json()["assumptions"]

    assert assumptions["exchange_rate"] == {
        "base_currency": "USD",
        "quote_currency": "TRY",
        "rate": "40",
        "date": "2026-11-23",
        "overridden": False,
    }
    assert assumptions["pricing"] == {
        "bos_price_per_kwp": {"amount": "100", "currency": "USD"},
        "labour_price_per_kwp": {"amount": "3000", "currency": "TRY"},
        "fixed_project_cost": {"amount": "20000", "currency": "TRY"},
        "margin": "0.25",
        "vat_rate": "0.20",
        "validity_period_days": 15,
    }
    assert assumptions["dc_ac_ratio_range"] == {"minimum": "1.00", "maximum": "1.30"}
    inverters = {i["inverter_id"]: i for i in assumptions["inverters"]}
    assert set(inverters) == {"i05", "i25", "i3", "i35", "i4", "i6", "i8"}
    assert inverters["i35"]["unit_price"] == {"amount": "650", "currency": "USD"}
    assert inverters["i35"]["ac_power_kw"] == 3.5


def test_money_rates_ratios_and_tariff_prices_are_decimal_strings_without_a_float_round_trip(
    client: TestClient,
) -> None:
    # 41.234567890123456789 has more digits than a float keeps; a string keeps them all.
    body = {
        **valid_body(),
        "exchange_rate_override": {"rate": "41.234567890123456789", "date": "2026-11-01"},
    }

    assumptions = client.post("/quotes", json=body).json()["assumptions"]

    assert assumptions["exchange_rate"]["rate"] == "41.234567890123456789"
    assert assumptions["tariff"] == {
        "tier_threshold_kwh_per_day": "8",
        "low_tariff_try_per_kwh": "3",
        "high_tariff_try_per_kwh": "5",
        "export_price_try_per_kwh": "2",
        "self_consumption_ratio": "0.8",
        "valid_from": "2026-04-04",
        "source": "test tariff",
    }
    assert assumptions["financial"]["tariff_escalation_rate_real"] == "0.02"
    assert assumptions["financial"]["equipment_escalation_rate_real"] == "0"
    assert assumptions["coverage_ratio"] == "0.80"
    assert assumptions["default_panel"]["degradation_rate_per_year"] == "0.005"
    assert assumptions["default_panel"]["unit_price"] == {"amount": "100", "currency": "USD"}


def test_displayed_figures_stay_rounded_numbers_next_to_the_string_assumptions(
    client: TestClient,
) -> None:
    quote = client.post("/quotes", json=valid_body()).json()
    option = quote["system_options"][0]

    assert option["capacity_kwp"] == 4.0
    assert isinstance(option["price"]["total_try"], int)
    assert isinstance(option["annual_production_kwh"], int)
    assert isinstance(option["savings"]["payback_period_years"], float)


def test_the_openapi_schema_declares_the_precision_sensitive_fields_as_strings(
    client: TestClient,
) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    def field_type(schema: str, field: str) -> Any:
        return schemas[schema]["properties"][field]["type"]

    assert field_type("MoneyResponse", "amount") == "string"
    assert field_type("ExchangeRateResponse", "rate") == "string"
    assert field_type("PricingResponse", "margin") == "string"
    assert field_type("PricingResponse", "vat_rate") == "string"
    assert field_type("TariffResponse", "low_tariff_try_per_kwh") == "string"
    assert field_type("TariffResponse", "export_price_try_per_kwh") == "string"
    assert field_type("FinancialResponse", "tariff_escalation_rate_real") == "string"
    assert field_type("DcAcRatioRangeResponse", "maximum") == "string"
    assert field_type("SystemOptionResponse", "capacity_kwp") == "number"
    assert "decimal string" in schemas["MoneyResponse"]["description"]
    assert "decimal string" in schemas["AssumptionsResponse"]["description"]


def test_tcmb_is_asked_for_the_usd_rate_of_the_quote_date(
    client: TestClient, exchange_rate_provider: FakeExchangeRateProvider
) -> None:
    client.post("/quotes", json=valid_body())

    assert exchange_rate_provider.requests == [(Currency.USD, QUOTE_DATE)]


def test_an_exchange_rate_override_is_used_and_tcmb_is_not_called(
    client: TestClient, exchange_rate_provider: FakeExchangeRateProvider
) -> None:
    body = {**valid_body(), "exchange_rate_override": {"rate": 45, "date": "2026-11-01"}}

    quote = client.post("/quotes", json=body).json()

    assert exchange_rate_provider.requests == []
    assert quote["assumptions"]["exchange_rate"] == {
        "base_currency": "USD",
        "quote_currency": "TRY",
        "rate": "45",
        "date": "2026-11-01",
        "overridden": True,
    }
    # USD 1,850 x 45 = 83,250 + 12,000 + 20,000 = 115,250; x 1.25 = 144,062.5; VAT 28,812.5
    assert quote["system_options"][0]["price"] == {
        "installation_cost_try": 115250,
        "sale_price_try": 144063,
        "vat_try": 28813,
        "total_try": 172875,
    }


def test_an_override_still_works_while_tcmb_is_down(
    client: TestClient, exchange_rate_provider: FakeExchangeRateProvider
) -> None:
    exchange_rate_provider.error = UpstreamUnavailableError("TCMB", "the request timed out")
    body = {**valid_body(), "exchange_rate_override": {"rate": 45, "date": "2026-11-01"}}

    assert client.post("/quotes", json=body).status_code == 201


@pytest.mark.parametrize(
    "override",
    [
        {"rate": 0, "date": "2026-11-01"},
        {"rate": -40, "date": "2026-11-01"},
        {"rate": 45},
        {"rate": 45, "date": "not-a-date"},
        {"date": "2026-11-01"},
    ],
)
def test_an_invalid_override_is_a_422_problem_naming_the_field(
    client: TestClient, override: dict[str, Any]
) -> None:
    response = client.post("/quotes", json={**valid_body(), "exchange_rate_override": override})

    assert response.status_code == 422
    assert response.json()["type"] == "urn:sunquote:problem:validation-error"
    fields = [error["field"] for error in response.json()["errors"]]
    assert any(field.startswith("exchange_rate_override") for field in fields)


def test_the_same_request_gives_the_same_quote(client: TestClient) -> None:
    first = client.post("/quotes", json=valid_body()).json()
    second = client.post("/quotes", json=valid_body()).json()

    # Only the identity differs: a new id, the next Quote Number and a later creation time.
    for identity in ("id", "quote_number", "created_at"):
        assert first.pop(identity) != second.pop(identity)
    assert first == second


def test_optional_customer_details_may_be_omitted(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("customer", {"name": "Mehmet Kaya"}))

    assert response.status_code == 201
    assert response.json()["customer"] == {"name": "Mehmet Kaya", "phone": None, "email": None}


def test_pvgis_is_asked_for_the_roof_orientation_at_the_site(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    body = with_change("roof.azimuth_deg", 225)
    body["roof"]["tilt_deg"] = 35

    client.post("/quotes", json=body)

    [query] = specific_yield_provider.queries
    assert (query.azimuth_deg, query.tilt_deg) == (Decimal("225"), Decimal("35"))
    assert query.coordinates.latitude == Decimal("39.9334")
    assert query.coordinates.longitude == Decimal("32.8597")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("customer.name", ""),
        ("customer.name", "   "),
        ("customer.name", ...),
        ("customer.email", "not-an-email"),
        ("site.latitude", 90.5),
        ("site.latitude", -91),
        ("site.longitude", 180.5),
        ("site.longitude", -181),
        ("site.latitude", ...),
        ("roof.usable_area_m2", 0),
        ("roof.usable_area_m2", -5),
        ("roof.azimuth_deg", ...),
        ("roof.azimuth_deg", None),
        ("roof.azimuth_deg", 360),
        ("roof.azimuth_deg", -1),
        ("roof.tilt_deg", ...),
        ("roof.tilt_deg", None),
        ("roof.tilt_deg", 90.5),
        ("roof.tilt_deg", -1),
        ("roof.roof_type", "gabled"),
        ("consumption.monthly_consumption_kwh", 0),
        ("consumption.monthly_consumption_kwh", -3),
        ("consumption.monthly_consumption_kwh", ...),
        ("consumption.monthly_consumption_kwh", None),
        ("consumption.monthly_bill_try", 0),
        ("consumption.monthly_bill_try", -3),
        ("subscriber_group", ...),
        ("contracted_power_kw", 0),
        ("contracted_power_kw", -3),
        ("contracted_power_kw", "lots"),
    ],
)
def test_invalid_input_is_a_422_problem_naming_the_field(
    client: TestClient, path: str, value: Any
) -> None:
    response = client.post("/quotes", json=with_change(path, value))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:validation-error"
    assert problem["status"] == 422
    assert path in [error["field"] for error in problem["errors"]]


def test_boundary_values_are_accepted(client: TestClient) -> None:
    body = valid_body()
    body["roof"].update(azimuth_deg=0, tilt_deg=0)
    body["site"].update(latitude=-90, longitude=180)

    assert client.post("/quotes", json=body).status_code == 201


@pytest.mark.parametrize(
    ("orientation", "recorded"),
    [
        ({}, {"azimuth_deg": None, "tilt_deg": None}),
        ({"azimuth_deg": 90, "tilt_deg": 30}, {"azimuth_deg": 90, "tilt_deg": 30}),
        ({"azimuth_deg": 270}, {"azimuth_deg": 270, "tilt_deg": None}),
        ({"azimuth_deg": None, "tilt_deg": 5}, {"azimuth_deg": None, "tilt_deg": 5}),
    ],
)
def test_flat_roof_uses_installer_orientation_and_records_the_submitted_angles(
    client: TestClient, orientation: dict[str, Any], recorded: dict[str, Any]
) -> None:
    body = valid_body()
    body["roof"] = {"roof_type": "flat", "usable_area_m2": 20, **orientation}

    response = client.post("/quotes", json=body)

    assert response.status_code == 201
    quote = response.json()
    [option] = quote["system_options"]
    assert option["panel_count"] == 5
    assumptions = quote["assumptions"]
    assert assumptions["roof_type"] == "flat"
    assert assumptions["effective_azimuth_deg"] == 180
    assert assumptions["effective_tilt_deg"] == 15
    assert assumptions["coverage_ratio"] == "0.50"
    assert assumptions["submitted_request"]["roof"] == {
        "roof_type": "flat",
        "usable_area_m2": 20,
        **recorded,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [("azimuth_deg", 360), ("azimuth_deg", -1), ("tilt_deg", 91), ("tilt_deg", "ignored")],
)
def test_flat_roof_angles_that_are_given_are_still_validated(
    client: TestClient, field: str, value: Any
) -> None:
    body = valid_body()
    body["roof"] = {"roof_type": "flat", "usable_area_m2": 20, field: value}

    response = client.post("/quotes", json=body)

    assert response.status_code == 422
    assert f"roof.{field}" in [error["field"] for error in response.json()["errors"]]


def test_flat_roof_does_not_need_angles(client: TestClient) -> None:
    body = valid_body()
    body["roof"] = {"roof_type": "flat", "usable_area_m2": 20}

    assert client.post("/quotes", json=body).status_code == 201


def test_malformed_json_is_a_validation_problem(client: TestClient) -> None:
    response = client.post(
        "/quotes", content="{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.json()["type"] == "urn:sunquote:problem:validation-error"


@pytest.mark.parametrize("group", ["commercial", "Residential", ""])
def test_other_subscriber_groups_are_unsupported(client: TestClient, group: str) -> None:
    response = client.post("/quotes", json=with_change("subscriber_group", group))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:unsupported-subscriber-group"
    assert problem["title"] == "Unsupported Subscriber Group"
    assert "residential" in problem["detail"]


def test_a_roof_that_fits_no_panel_is_a_no_viable_system_problem(client: TestClient) -> None:
    response = client.post("/quotes", json=with_change("roof.usable_area_m2", 2))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:no-viable-system"
    assert problem["status"] == 422


def test_pvgis_outage_is_a_503_problem(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    specific_yield_provider.error = UpstreamUnavailableError("PVGIS", "the request timed out")

    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:upstream-unavailable"
    assert problem["status"] == 503
    assert "PVGIS" in problem["detail"]


def test_tcmb_outage_is_a_503_problem(
    client: TestClient, exchange_rate_provider: FakeExchangeRateProvider
) -> None:
    exchange_rate_provider.error = UpstreamUnavailableError("TCMB", "the request timed out")

    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:upstream-unavailable"
    assert "TCMB" in problem["detail"]


def test_a_system_no_inverter_fits_is_a_no_compatible_inverter_problem(
    client: TestClient,
) -> None:
    # 6 m2 x 0.80 / 2.0 m2 = 2 panels = 1.0 kWp: the smallest test inverter (0.5 kW) gives a
    # DC/AC Ratio of 2.0, above the 1.30 maximum, and every other one is oversized.
    response = client.post("/quotes", json=with_change("roof.usable_area_m2", 6))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:no-compatible-inverter"
    assert problem["title"] == "No compatible inverter"
    assert problem["status"] == 422
    assert "1.00 kWp" in problem["detail"]


def test_the_no_compatible_inverter_detail_shows_the_capacity_rounded_by_the_policy(
    client_factory: ClientFactory,
) -> None:
    odd_panel = replace(make_panel(), panel_id="odd-437w", power_w=437)  # 2 panels = 0.874 kWp
    catalog = Catalog(
        panels=(odd_panel,), default_panel_id=odd_panel.panel_id, inverters=DEFAULT_INVERTERS
    )
    odd_client = client_factory(reference_data=make_reference_data(catalog=catalog))

    response = odd_client.post("/quotes", json=with_change("roof.usable_area_m2", 6))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "0.87 kWp" in detail
    assert "0.874" not in detail


def test_a_failed_quote_does_not_use_up_a_quote_number(
    client: TestClient,
    quote_repository: FakeQuoteRepository,
    specific_yield_provider: FakeSpecificYieldProvider,
) -> None:
    unviable = client.post("/quotes", json=with_change("roof.usable_area_m2", 1))
    no_inverter = client.post("/quotes", json=with_change("roof.usable_area_m2", 6))
    specific_yield_provider.error = UpstreamUnavailableError("PVGIS", "the request timed out")
    outage = client.post("/quotes", json=valid_body())
    specific_yield_provider.error = None

    created = client.post("/quotes", json=valid_body())

    assert (unviable.status_code, no_inverter.status_code, outage.status_code) == (422, 422, 503)
    assert created.status_code == 201
    assert created.json()["quote_number"] == "SQ-2026-000001"
    assert quote_repository.issued_numbers == ["SQ-2026-000001"]


@pytest.mark.parametrize(
    ("quote_date", "valid_until"),
    [
        (date(2026, 12, 17), "2027-01-01"),  # the first day of the next year
        (date(2026, 12, 20), "2027-01-04"),
        (date(2026, 12, 31), "2027-01-15"),
    ],
)
def test_valid_until_crosses_into_the_next_year(
    client_factory: ClientFactory, quote_date: date, valid_until: str
) -> None:
    year_end_client = client_factory(clock=FixedClock(quote_date))

    quote = year_end_client.post("/quotes", json=valid_body()).json()

    assert quote["quote_date"] == quote_date.isoformat()
    assert quote["valid_until"] == valid_until  # quote date + the 15-day Validity Period
    assert quote["quote_number"] == "SQ-2026-000001"  # numbered by the quote date's year


def test_a_location_pvgis_rejects_is_a_422_problem_carrying_its_message(
    client: TestClient, specific_yield_provider: FakeSpecificYieldProvider
) -> None:
    specific_yield_provider.error = LocationNotSupportedError(
        "Location over the sea. Please, select another location"
    )

    response = client.post("/quotes", json=valid_body())

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    problem = response.json()
    assert problem["type"] == "urn:sunquote:problem:location-not-supported"
    assert problem["title"] == "Location not supported"
    assert problem["detail"] == "Location over the sea. Please, select another location"


def test_openapi_documents_the_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "201" in paths["/quotes"]["post"]["responses"]


# --- Savings, payback and the tariff assumptions -------------------------------------------
#
# The default Consumption-Matched 4.0 kWp system (500 kWh/month, 6,000 kWh a year, total price
# 159,000 TRY) and the Roof-Max 8.0 kWp one (12,000 kWh, 8 kW inverter, total 276,000 TRY), with
# the test tariff and financial assumptions of tests/factories.py. Year-by-year figures were
# worked out by hand (see tests/domain/test_build_quote.py).


def test_each_option_carries_first_year_savings_payback_and_lifetime_savings(
    client: TestClient,
) -> None:
    matched, roof_max = client.post("/quotes", json=valid_body()).json()["system_options"]

    savings = matched["savings"]
    assert savings["first_year_annual_savings_try"] == 22960
    assert savings["payback_period_years"] == 6.6  # 6.6132, shown with one decimal
    assert savings["payback_beyond_lifetime"] is False
    assert savings["lifetime_savings_try"] == 670530  # 670,530.39, net of the replacement
    # The Roof-Max option has its own savings: 12,000 kWh produced, the whole 6,000 kWh bill
    # saved (24,160) plus 6,000 kWh exported at 2 (12,000), and a 52,800 TRY inverter replacement.
    roof_max_savings = roof_max["savings"]
    assert roof_max_savings["first_year_annual_savings_try"] == 36160
    assert roof_max_savings["payback_period_years"] == 7.2  # 7.2439
    assert roof_max_savings["lifetime_savings_try"] == 1057294  # 1,057,293.79
    assert roof_max_savings["cash_flow"][11]["inverter_replacement_try"] == 52800


def test_the_yearly_cash_flow_is_returned_in_whole_lira_and_kwh(client: TestClient) -> None:
    option = client.post("/quotes", json=valid_body()).json()["system_options"][0]

    cash_flow = option["savings"]["cash_flow"]
    assert [row["year"] for row in cash_flow] == list(range(1, 26))
    assert cash_flow[0] == {
        "year": 1,
        "production_kwh": 6000,
        "self_consumed_kwh": 4800,
        "exported_kwh": 1200,
        "self_consumption_savings_try": 20560,
        "export_income_try": 2400,
        "annual_savings_try": 22960,
        "inverter_replacement_try": 0,
        "net_savings_try": 22960,
        "cumulative_net_savings_try": 22960,
    }
    # Year 12 carries the 31,200 TRY inverter replacement: 27,427.29 - 31,200 = -3,772.71.
    year_twelve = cash_flow[11]
    assert year_twelve["inverter_replacement_try"] == 31200
    assert year_twelve["net_savings_try"] == -3773
    assert year_twelve["cumulative_net_savings_try"] == 270388


def test_a_payback_beyond_the_lifetime_has_no_period_and_says_so(client: TestClient) -> None:
    body = valid_body()
    body["consumption"]["monthly_consumption_kwh"] = 10  # one panel; the fixed costs dominate

    option = client.post("/quotes", json=body).json()["system_options"][0]

    savings = option["savings"]
    assert savings["payback_beyond_lifetime"] is True
    assert savings["payback_period_years"] is None


def test_assumptions_record_consumption_split_tariff_and_financial_inputs(
    client: TestClient,
) -> None:
    assumptions = client.post("/quotes", json=valid_body()).json()["assumptions"]

    assert assumptions["annual_consumption_kwh"] == 6000
    assert assumptions["low_tier_consumption_kwh"] == 2920
    assert assumptions["high_tier_consumption_kwh"] == 3080
    assert assumptions["tariff"] == {
        "tier_threshold_kwh_per_day": "8",
        "low_tariff_try_per_kwh": "3",
        "high_tariff_try_per_kwh": "5",
        "export_price_try_per_kwh": "2",
        "self_consumption_ratio": "0.8",
        "valid_from": "2026-04-04",
        "source": "test tariff",
    }
    assert assumptions["financial"] == {
        "tariff_escalation_rate_real": "0.02",
        "equipment_escalation_rate_real": "0",
        "lifetime_years": 25,
        "inverter_replacement_year": 12,
    }
    assert assumptions["default_panel"]["degradation_rate_per_year"] == "0.005"
