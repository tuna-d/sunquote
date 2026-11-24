"""The Narrative step of POST /quotes, through the real app with a scripted fake writer.

Fixed inputs as in tests/api/test_quotes.py: the default request gets two System Options.
With `usable_area_m2` 20 it gets one. What reaches the Customer is the document text and the
Quote JSON; the tests assert on those and on what the writer was given, not on prompt wording.
"""

import asyncio
from dataclasses import asdict, replace
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sunquote.api import turkish
from sunquote.api.document import fixed_draft
from sunquote.domain.errors import NarrativeUnavailableError
from sunquote.domain.narrative import (
    NarrativeContext,
    NarrativeDraft,
    ViolationKind,
    validate_narrative,
)
from tests.api.test_quotes import valid_body, with_change
from tests.conftest import ClientFactory
from tests.fakes import FakeQuoteRepository, ScriptedNarrativeWriter

GREETING = "Merhaba {customer_name}, teklifiniz hazır."
SUMMARY = (
    "Önerilen {option_1_capacity_kwp} kWp güçteki sistem yılda {option_1_annual_production_kwh} "
    "kWh üretir. Çatınız boyutu belirledi."
)
COMPARISON = (
    "Daha büyük ikinci seçenek {option_2_total_try} tutarındadır; geri ödemesi "
    "{option_2_payback_years} yıldır."
)
NEXT_STEPS = "Önce keşif yapılır. Teklif {valid_until} tarihine kadar geçerlidir."


def draft(*, comparison: bool = True, **changes: str | None) -> NarrativeDraft:
    base = NarrativeDraft(
        greeting=GREETING,
        summary=SUMMARY,
        next_steps=NEXT_STEPS,
        options_comparison=COMPARISON if comparison else None,
    )
    return replace(base, **changes)


def one_option_body() -> dict[str, Any]:
    return with_change("roof.usable_area_m2", 20)


def create(
    client: TestClient, body: dict[str, Any] | None = None, *, status: int = 201
) -> dict[str, Any]:
    response = client.post("/quotes", json=body or valid_body())
    assert response.status_code == status, response.text
    created: dict[str, Any] = response.json()
    return created


def page(client: TestClient, quote: dict[str, Any]) -> str:
    response = client.get(f"/quotes/{quote['id']}/document")
    assert response.status_code == 200
    return response.text


def slot(html: str, name: str) -> str:
    return html.split(f'data-slot="{name}">')[1].split("</p>")[0]


def client_with(client_factory: ClientFactory, writer: ScriptedNarrativeWriter) -> TestClient:
    return client_factory(narrative_writer=writer)


# --- A valid draft --------------------------------------------------------------------------


def test_a_valid_draft_is_shown_in_the_document_with_every_figure_filled_from_the_quote(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(draft(), model_name="gemini-test")
    client = client_with(client_factory, writer)

    quote = create(client)
    html = page(client, quote)

    first, second = quote["system_options"]
    assert writer.calls == 1
    assert slot(html, "greeting") == "Merhaba Şule Öztürk, teklifiniz hazır."
    capacity = turkish.format_decimal(Decimal(str(first["capacity_kwp"])).quantize(Decimal("0.01")))
    production = turkish.format_int(first["annual_production_kwh"])
    assert slot(html, "summary") == (
        f"Önerilen {capacity} kWp güçteki sistem yılda {production} kWh üretir. "
        "Çatınız boyutu belirledi."
    )
    payback = turkish.format_decimal(
        Decimal(str(second["savings"]["payback_period_years"])).quantize(Decimal("0.1"))
    )
    total = turkish.format_try(second["price"]["total_try"])
    assert slot(html, "options_comparison") == (
        f"Daha büyük ikinci seçenek {total} tutarındadır; geri ödemesi {payback} yıldır."
    )
    assert slot(html, "next_steps") == (
        "Önce keşif yapılır. Teklif 09.12.2026 tarihine kadar geçerlidir."
    )
    assert "Sistem seçenekleri" in html
    assert "{" not in html.split("<body")[1]


def test_every_placeholder_is_filled_with_the_figure_the_tables_show(
    client_factory: ClientFactory,
) -> None:
    names = [
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
    ]
    quote_level = ["customer_name", "quote_number", "valid_until", "validity_period_days"]
    text = " | ".join(
        [f"{{{name}}}" for name in quote_level]
        + [f"{{option_{n}_{name}}}" for n in (1, 2) for name in names]
    )
    # Digits only inside placeholders, so the draft is valid.
    writer = ScriptedNarrativeWriter(draft(summary=text))
    client = client_with(client_factory, writer)

    quote = create(client)
    summary = slot(page(client, quote), "summary").split(" | ")

    assert summary[:4] == ["Şule Öztürk", quote["quote_number"], "09.12.2026", "15"]
    for number, option in enumerate(quote["system_options"]):
        filled = summary[4 + number * len(names) : 4 + (number + 1) * len(names)]
        savings, price = option["savings"], option["price"]
        assert filled == [
            turkish.format_decimal(Decimal(str(option["capacity_kwp"])).quantize(Decimal("0.01"))),
            str(option["panel_count"]),
            f"{option['panel']['manufacturer']} {option['panel']['model']}",
            f"{option['inverter']['manufacturer']} {option['inverter']['model']}",
            turkish.format_int(option["annual_production_kwh"]),
            turkish.format_try(price["sale_price_try"]),
            turkish.format_try(price["vat_try"]),
            turkish.format_try(price["total_try"]),
            turkish.format_try(savings["first_year_annual_savings_try"]),
            turkish.format_decimal(
                Decimal(str(savings["payback_period_years"])).quantize(Decimal("0.1"))
            ),
            turkish.format_try(savings["lifetime_savings_try"]),
        ]


def test_the_quote_json_carries_the_narrative_with_placeholders_filled(
    client_factory: ClientFactory,
) -> None:
    client = client_with(client_factory, ScriptedNarrativeWriter(draft(), model_name="gemini-t"))

    created = create(client)
    fetched = client.get(f"/quotes/{created['id']}").json()

    for quote in (created, fetched):
        narrative = quote["narrative"]
        assert narrative["source"] == "llm"
        assert narrative["model"] == "gemini-t"
        assert narrative["generated_at"].startswith("2026-11-24T09:30:00")
        assert narrative["greeting"] == "Merhaba Şule Öztürk, teklifiniz hazır."
        assert narrative["next_steps"].endswith("09.12.2026 tarihine kadar geçerlidir.")
        assert "{" not in "".join(
            str(narrative[key]) for key in ("greeting", "summary", "options_comparison")
        )
        assert narrative["options_comparison"].startswith("Daha büyük ikinci seçenek")
    assert fetched == created


# --- The retry ------------------------------------------------------------------------------


def test_a_stray_digit_is_retried_with_the_violations_and_the_second_draft_is_used(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(
        draft(summary="Sistem 8,4 kWp gücündedir."), draft(summary="Sistem sağlamdır.")
    )
    client = client_with(client_factory, writer)

    quote = create(client)
    html = page(client, quote)

    assert writer.calls == 2
    assert writer.violations[0] == ()
    assert [(v.kind, v.field) for v in writer.violations[1]] == [
        (ViolationKind.DIGIT_OUTSIDE_PLACEHOLDER, "summary")
    ]
    assert quote["narrative"]["source"] == "llm"
    assert slot(html, "summary") == "Sistem sağlamdır."
    assert "8,4" not in html


def test_two_invalid_drafts_give_the_fixed_text_and_a_fallback(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(
        draft(summary="Sistem 8,4 kWp."), draft(summary="Bu {unknown} bir şey.")
    )
    client = client_with(client_factory, writer)

    quote = create(client)
    html = page(client, quote)

    assert writer.calls == 2
    assert quote["narrative"]["source"] == "fallback"
    assert quote["narrative"]["model"] is None
    assert slot(html, "greeting") == "Sayın Şule Öztürk,"
    assert "8,4 kWp." not in html
    assert "{unknown}" not in html


@pytest.mark.parametrize(
    "script",
    [
        [NarrativeUnavailableError("rate limited")],
        [0.5],
        [draft(summary="Sistem 8 kWp."), NarrativeUnavailableError("down")],
        [draft(summary="Sistem 8 kWp."), 0.5],
    ],
    ids=["error", "timeout", "error-on-retry", "timeout-on-retry"],
)
def test_an_error_or_timeout_gives_the_fixed_text_and_the_quote_is_still_created(
    client_factory: ClientFactory,
    quote_repository: FakeQuoteRepository,
    script: list[Any],
) -> None:
    writer = ScriptedNarrativeWriter(*script)
    client = client_factory(narrative_writer=writer, narrative_budget_seconds=0.1)

    quote = create(client)

    assert quote["narrative"]["source"] == "fallback"
    assert quote["narrative"]["greeting"] == "Sayın Şule Öztürk,"
    assert len(quote_repository.stored) == 1
    assert slot(page(client, quote), "greeting") == "Sayın Şule Öztürk,"


def test_any_unexpected_writer_exception_still_gives_a_fallback_and_a_201(
    client_factory: ClientFactory,
    quote_repository: FakeQuoteRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer = ScriptedNarrativeWriter(RuntimeError("boom with key=SECRET-KEY"))
    client = client_with(client_factory, writer)

    with caplog.at_level("WARNING"):
        quote = create(client)

    assert quote["narrative"]["source"] == "fallback"
    assert quote["narrative"]["greeting"] == "Sayın Şule Öztürk,"
    assert len(quote_repository.stored) == 1
    assert any("RuntimeError" in message for message in caplog.messages)
    # The log names the exception type only: an arbitrary message could carry a secret.
    assert "SECRET-KEY" not in caplog.text


def test_an_error_on_the_first_attempt_is_not_retried(client_factory: ClientFactory) -> None:
    writer = ScriptedNarrativeWriter(NarrativeUnavailableError("down"), draft())
    client = client_with(client_factory, writer)

    create(client)

    assert writer.calls == 1


def test_both_attempts_share_one_time_budget(client_factory: ClientFactory) -> None:
    # Each attempt alone (0.07 s) is within the 0.1 s budget; together they are not.
    class SlowWriter(ScriptedNarrativeWriter):
        async def write(
            self, context: NarrativeContext, *, previous_violations: Any = ()
        ) -> NarrativeDraft:
            await asyncio.sleep(0.07)
            return await super().write(context, previous_violations=previous_violations)

    writer = SlowWriter(draft(summary="Sistem 8 kWp."), draft())
    client = client_factory(narrative_writer=writer, narrative_budget_seconds=0.1)

    quote = create(client)

    assert quote["narrative"]["source"] == "fallback"


def test_no_writer_gives_a_fallback_and_the_fixed_text(client: TestClient) -> None:
    quote = create(client)

    assert quote["narrative"]["source"] == "fallback"
    assert quote["narrative"]["model"] is None
    assert slot(page(client, quote), "greeting") == "Sayın Şule Öztürk,"


def test_a_fallback_narrative_is_the_fixed_text_with_its_figures_filled(
    client: TestClient,
) -> None:
    quote = create(client)
    narrative = quote["narrative"]
    first = quote["system_options"][0]

    assert narrative["generated_at"].startswith("2026-11-24T09:30:00")
    assert narrative["greeting"] == "Sayın Şule Öztürk,"
    assert turkish.format_try(first["price"]["total_try"]) in narrative["summary"]
    assert "{" not in "".join(str(value) for value in narrative.values())
    assert narrative["options_comparison"] is not None


# --- One or two options ---------------------------------------------------------------------


def test_a_single_option_has_no_comparison(client_factory: ClientFactory) -> None:
    writer = ScriptedNarrativeWriter(draft(comparison=False))
    client = client_with(client_factory, writer)

    quote = create(client, one_option_body())
    html = page(client, quote)

    assert len(quote["system_options"]) == 1
    assert quote["narrative"]["source"] == "llm"
    assert quote["narrative"]["options_comparison"] is None
    assert 'data-slot="options_comparison"' not in html


def test_a_draft_with_a_comparison_for_a_single_option_is_rejected(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(
        draft(options_comparison="{option_1_total_try} tutarındadır."), draft(comparison=False)
    )
    client = client_with(client_factory, writer)

    quote = create(client, one_option_body())

    assert [(v.kind, v.field) for v in writer.violations[1]] == [
        (ViolationKind.UNEXPECTED_COMPARISON, "options_comparison")
    ]
    assert quote["narrative"]["source"] == "llm"
    assert quote["narrative"]["options_comparison"] is None


def test_a_draft_that_names_option_2_for_a_single_option_is_rejected(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(
        draft(comparison=False, summary="{option_2_total_try}"),
        draft(comparison=False, summary="{option_2_total_try}"),
    )
    client = client_with(client_factory, writer)

    quote = create(client, one_option_body())

    assert quote["narrative"]["source"] == "fallback"


def test_a_missing_comparison_with_two_options_is_rejected(client_factory: ClientFactory) -> None:
    writer = ScriptedNarrativeWriter(draft(comparison=False), draft())
    client = client_with(client_factory, writer)

    quote = create(client)

    assert [(v.kind, v.field) for v in writer.violations[1]] == [
        (ViolationKind.MISSING_FIELD, "options_comparison")
    ]
    assert quote["narrative"]["source"] == "llm"


# --- Personal data --------------------------------------------------------------------------


def test_the_customers_name_address_and_coordinates_reach_the_writer_nowhere(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(
        draft(summary="Sistem 8 kWp."), draft(summary="Sistem sağlamdır.")
    )
    client = client_with(client_factory, writer)
    body = valid_body()
    del body["site"]["latitude"], body["site"]["longitude"]
    body["site"]["address"] = "Atatürk Bulvarı Çankaya Ankara"

    create(client, body)

    assert writer.calls == 2
    handed_over = " ".join(repr(asdict(context)) for context in writer.contexts) + " ".join(
        repr(violations) for violations in writer.violations
    )
    for secret in (
        "Şule",
        "Öztürk",
        "Atatürk Bulvarı",
        "Çankaya",
        "Anıtkabir",  # the geocoder's resolved match
        "Ankara",
        "39.92",
        "32.83",
        "39.93",
        "32.85",
        "sule@example.com",
        "555",
    ):
        assert secret not in handed_over, secret


# --- Stored ---------------------------------------------------------------------------------


def test_a_stored_quote_shows_the_same_narrative_on_every_read(
    client_factory: ClientFactory,
) -> None:
    writer = ScriptedNarrativeWriter(draft(), draft(summary="Başka bir özet."))
    client = client_with(client_factory, writer)
    quote = create(client)

    pages = [page(client, quote) for _ in range(3)]
    reads = [client.get(f"/quotes/{quote['id']}").json()["narrative"] for _ in range(3)]

    assert pages[0] == pages[1] == pages[2]
    assert reads == [quote["narrative"]] * 3
    assert writer.calls == 1  # reading never writes again


# --- The fixed text -------------------------------------------------------------------------


@pytest.mark.parametrize("options", [1, 2])
def test_the_fixed_text_passes_the_validator(client_factory: ClientFactory, options: int) -> None:
    contexts: list[NarrativeContext] = []

    class Spy(ScriptedNarrativeWriter):
        async def write(
            self, context: NarrativeContext, *, previous_violations: Any = ()
        ) -> NarrativeDraft:
            contexts.append(context)
            raise NarrativeUnavailableError("stop")

    client = client_factory(narrative_writer=Spy())
    create(client, one_option_body() if options == 1 else valid_body())

    context = contexts[0]
    assert context.option_count == options
    assert validate_narrative(fixed_draft(options), context) == ()


def test_the_fixed_text_names_only_placeholders_the_quote_offers() -> None:
    for count in (1, 2):
        draft_text = fixed_draft(count)
        assert (draft_text.options_comparison is not None) is (count == 2)
        assert "option_2_" not in (draft_text.summary + draft_text.next_steps)
