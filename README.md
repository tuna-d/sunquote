<img src="assets/icon.svg" width="64" height="64" alt="">

# sunquote

sunquote prepares residential rooftop solar Quotes for Turkish Installers. A Sales Rep enters
the Customer, the Site's Address or Coordinates, the Roof and the average Monthly Consumption
or Monthly Bill. The service sizes up to two System Options (Consumption-Matched and Roof-Max),
selects the panel and inverter, estimates production, prices the installation, and calculates
Annual Savings and the Payback Period.

Each Quote is stored with its Assumptions and can be opened as a printable Turkish document.
The bundled Catalog, Tariff and pricing inputs are [placeholder data](#placeholder-data).

## Run with Docker Compose

From the repository root, with Docker running:

```sh
docker compose up --build
```

No `.env` or API keys are required. Compose starts the API, Postgres and Redis. The API
applies the Alembic migrations at startup. Run `docker compose ps` in another terminal to
check that all three services are healthy.

Open [Swagger UI](http://localhost:8000/docs) to try the API, or check
[service health](http://localhost:8000/health). Set `API_HOST_PORT` in your shell to use
another host port and use that port in the walkthrough. [`.env.example`](.env.example)
lists optional settings, including the published Postgres and Redis ports.

Quote creation needs internet access to the public providers listed under
[Architecture](#architecture). If a provider is unavailable and Redis has no cached value,
the API returns a `503` and stores no Quote.

## Create, list and open a Quote

### Create a Quote for an Ankara Address

Run the following in a POSIX shell, or paste the JSON body into `POST /quotes` in Swagger UI.

```sh
curl -i http://localhost:8000/quotes -H 'Content-Type: application/json' -d '{
  "customer": {"name": "Demo Customer"},
  "site": {"address": "Anıtkabir, Ankara"},
  "roof": {"roof_type": "pitched", "usable_area_m2": 40, "azimuth_deg": 180, "tilt_deg": 30},
  "consumption": {"monthly_consumption_kwh": 500},
  "subscriber_group": "residential"
}'
```

The response is `201 Created`. Copy the returned `id` (UUID). The response also includes
the Quote Number, quote date and valid-until date, System Options with monthly production and yearly
cash flow, and the Assumptions used to calculate them. Prices are shown in whole lira.
In the Assumptions, money, rates, ratios and tariff prices are decimal strings at full
precision (never a float), and measurements such as coordinates and angles are numbers.

You can provide both `latitude` and `longitude` in `site` to skip Address lookup. The
API uses those Coordinates when both forms are present. For a flat Roof, use
`"roof": {"roof_type": "flat", "usable_area_m2": 40}` to use the configured tilt and
south-facing azimuth (an `azimuth_deg` or `tilt_deg` you add is recorded as submitted but not
used). A system is capped by the Contracted Power: the panel count follows the largest Catalog
inverter whose AC power is at most the Contracted Power. For consumption based on the bill, send `monthly_bill_try` instead
of `monthly_consumption_kwh`. If both are present, consumption in kWh takes precedence.

### List and open the stored Quote

```sh
curl 'http://localhost:8000/quotes?page=1&page_size=20'
```

The `200 OK` response lists Quotes newest first in `items`. Find the entry with the UUID
you copied. The example is listed with the Customer name, district and province from
geocoding, Quote Number, creation time, System Option count, and the first option's
capacity and total price.

Replace `{id}` below with that UUID.

| Endpoint | Result |
| --- | --- |
| `GET /quotes/{id}` | Opens the stored Quote as JSON. |
| `GET /quotes/{id}/document` | Opens the printable Turkish HTML document. |

In your browser, visit `http://localhost:8000/quotes/{id}/document` and use the print
dialog to print the Quote or save it as a PDF.

Stored Quotes are immutable. The Quote Number sequence restarts each year, and a request that
fails validation, finds no viable system or hits an unavailable upstream does not use up a
number. API errors use
RFC 9457 `application/problem+json` with a stable `type`. Unknown Quote IDs return `404`.

## Architecture

- [`domain`](src/sunquote/domain) holds the calculation engine and defines ports for the
  Geocoder, Specific Yield provider, Exchange Rate provider, Quote repository and Clock.
  The calculation takes its inputs explicitly.
- [`api`](src/sunquote/api) handles FastAPI requests, Pydantic validation, error mapping and
  response rendering. Jinja2 renders the Turkish document from the stored Quote.
- [`adapters`](src/sunquote/adapters) implement the ports and load the bundled TOML data.
  [`bootstrap.py`](src/sunquote/bootstrap.py) wires them into the application.

[Nominatim](https://nominatim.openstreetmap.org/) resolves Turkish Addresses using
[© OpenStreetMap contributors](https://www.openstreetmap.org/copyright) data. When using the
public endpoint, follow its [usage policy](https://operations.osmfoundation.org/policies/nominatim/),
including the application-wide one-request-per-second limit and privacy rules.
`SUNQUOTE_NOMINATIM_BASE_URL` can point to another instance.

[PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/) provides Specific Yield for the Site and
effective Roof angles. [TCMB](https://www.tcmb.gov.tr/kurlar/kurlar_tr.html) provides the
forex selling rate from the latest published business day before the Quote date.
An `exchange_rate_override` containing a `rate` and `date` bypasses the TCMB lookup.

Postgres stores Quotes through async SQLAlchemy and asyncpg. Redis caches geocoding and
Specific Yield for 30 days and keeps Exchange Rates by Quote date and currency without
expiry. If Redis is unreachable, the API calls the providers directly.

## Run locally

With Python 3.13 and [uv](https://docs.astral.sh/uv/) installed, start the backing services
and run the API on a separate port:

```sh
docker compose up -d --wait postgres redis
uv sync
SUNQUOTE_REDIS_URL=redis://127.0.0.1:6379/0 uv run fastapi dev src/sunquote/api/app.py --port 8102
```

The API defaults to the Postgres URL published on localhost by Compose. Redis caching is
optional outside Compose. Use [`.env.example`](.env.example) to configure either service.

## Optional: LLM-written Narrative

Every Quote document opens with a greeting, a summary, a comparison of the System Options
(when there are two) and next steps. Without a key these are fixed Turkish paragraphs. With a
free Gemini API key, Gemini writes them for each new Quote:

1. Create a key at [Google AI Studio](https://aistudio.google.com/apikey). The free tier needs
   no billing.
2. Copy [`.env.example`](.env.example) to `.env` and set `SUNQUOTE_GEMINI_API_KEY=<your key>`.
   `.env` is not committed. Then run `docker compose up --build` (Compose passes the key
   through) or the local command above.
3. Create a Quote. Its JSON shows `narrative.source: "llm"` and the model that wrote it.

The default model, `gemini-3.5-flash-lite`, is on the Gemini API free tier. Checked on
Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing) on 2026-11-24; free-tier
availability changes between models and dates, so re-check before relying on it.
`SUNQUOTE_GEMINI_MODEL` selects another model. The project never assumes a paid tier.

**Privacy.** Google's free tier may use submitted content to improve its products. Only an
anonymised description of the Quote is sent: option count, sizing strategy and binding limit,
roof type and orientation as a word, booleans such as which option costs more, and the list of
placeholders. No Customer name, Address, Coordinates, phone, email or figure leaves the service.

**Figures.** The model never writes a figure. It refers to figures and to the Customer through
placeholders such as `{option_1_capacity_kwp}`, and the template fills them from the calculated
values ([ADR 0001](docs/adr/0001-llm-never-writes-figures.md)). Output with a digit outside a
placeholder, an unknown placeholder or a missing section is rejected and requested once more.

**Fallback.** With no key, a rate limit (HTTP 429), a timeout (the two attempts share
`SUNQUOTE_NARRATIVE_TIMEOUT_SECONDS`, 15 s), a network error, a blocked or malformed answer, or
a second rejected draft, the Quote still succeeds: it uses the fixed Turkish text and records
`narrative.source: "fallback"`. The key never appears in logs or error messages.

### Run the Narrative eval

Set `SUNQUOTE_GEMINI_API_KEY` in `.env` or the shell and run from the repository root:

```sh
uv run pytest -m eval -rs
```

The eval skips when the key is unset. With a key, it builds 20 Quotes from fixed test inputs,
uses the configured Gemini model, and prints a table of results by scenario and grader. A
scenario passes when the final draft clears every validator rule and the Turkish number-word
check. The number-word check is eval-only and treats `bir` as an indefinite article. A fallback
fails the scenario. If the last attempt yields no draft, each grader shows `-` and receives no
credit for that scenario. The run requires at least 18 of 20 Quotes to pass (90%).

The eval waits 15 seconds between Gemini requests, including retries. Set
`SUNQUOTE_EVAL_DELAY_SECONDS` in `.env` or the shell to adjust the pause. A run makes 20 to 40
requests, depending on retries. Check your project's free-tier per-minute and daily limits in
[Google AI Studio](https://aistudio.google.com/rate-limit).

The live eval is opt-in and excluded from CI. The default offline suite checks the set's coverage
of System Option count, Roof Type, Binding Limit, Tariff Tier, Payback Period and both forms of
consumption input.

## Optional: the quote assistant

`POST /assistant/messages` lets a Sales Rep describe a Customer in Turkish instead of filling in
the `POST /quotes` form. It needs the same free Gemini key as the Narrative
(`SUNQUOTE_GEMINI_API_KEY`, see above). Without a key it answers `503` with the problem type
`urn:sunquote:problem:assistant-not-configured`, and the rest of the API works as usual.

```sh
curl http://localhost:8000/assistant/messages -H 'Content-Type: application/json' -d '{
  "messages": [
    {"role": "user", "content": "Ayşe Yılmaz için teklif: Etimesgut, Ankara. 40 m² eğimli çatı, güneye bakıyor, 30 derece. Aylık 500 kWh tüketiyor."}
  ]
}'
```

Gemini turns the message into a `create_quote` tool call, which runs the normal Quote creation
(geocoding, PVGIS, TCMB, Narrative, storage). The response has three fields:

- `reply`: a Turkish explanation of the Quote with every figure filled from the Quote;
- `quote`: `{id, quote_number, document_url}` when a Quote was created in this turn, else `null`;
- `missing_fields`: an empty list for now.

The server keeps no conversation: the client sends the whole conversation (1 to 20 messages of
at most 2,000 characters, the last one from `user`) with every request. The model never
supplies Coordinates, since the tool takes only an Address, which is always geocoded. At most one
Quote is created per request and the model is called at most three times, within
`SUNQUOTE_ASSISTANT_TIMEOUT_SECONDS` (30 s).

**Figures.** As with the Narrative, the model refers to figures through placeholders and the
service fills them ([ADR 0001](docs/adr/0001-llm-never-writes-figures.md)). A reply that breaks
the rules is requested once more. If it breaks them again, or the model fails after the Quote was
created, the reply is a fixed Turkish confirmation with the Quote Number, each option's capacity
and total price, and the document link. When the model is unavailable before any Quote exists,
the endpoint answers `503` with `urn:sunquote:problem:assistant-unavailable`.

**Privacy.** Unlike the Narrative, the Sales Rep's own messages go to Gemini and may include the
Customer's name and Address. Google's free tier may use submitted content for training.

## Placeholder data

The TOML files in [`src/sunquote/data/`](src/sunquote/data) contain placeholder inputs
for the Catalog (panel and inverter specifications and unit prices), Residential Tariff
(tiers, Export Price, Self-Consumption Ratio and default Contracted Power), and
pricing, engineering and financial Assumptions (installation costs, Margin, VAT, Roof
coverage, system loss and escalation rates). Every price entry declares its own currency
(`price_currency` for Catalog items, `currency` for the pricing Assumptions); the Quote
fetches the TCMB rate for that currency (USD in the placeholder data) and records it. The
prices in one data set may use TRY and one foreign currency, not two.

The [market-data research note](docs/research/placeholder-market-data.md) records sources,
dates, owner decisions and open questions. Set `SUNQUOTE_DATA_DIR` to load your own files.
See the ADRs on [figures in the Quote document](docs/adr/0001-llm-never-writes-figures.md),
[marginal Tariff Tiers](docs/adr/0002-marginal-tariff-tiers.md) and
[real escalation rates](docs/adr/0003-real-escalation-rates.md).

## Tests and CI

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pytest -m integration
```

The default pytest run excludes the `integration` and `eval` markers. It includes
offline tests and the Postgres and Redis adapter contracts when their test URLs are
configured. To run those contracts locally, start the backing services with
`docker compose up -d --wait postgres redis`, then run:

```sh
SUNQUOTE_TEST_DATABASE_URL=postgresql+asyncpg://sunquote:sunquote@127.0.0.1:5432/sunquote \
SUNQUOTE_TEST_REDIS_URL=redis://127.0.0.1:6379/15 \
uv run pytest
```

Without the test URLs, the service-backed tests skip locally. The examples use `127.0.0.1`
because Compose publishes both services on IPv4 loopback. Update the URLs if you changed
the published ports. Postgres tests use temporary schemas, and Redis tests use a separate
database from the API cache.

[CI](.github/workflows/ci.yml) runs dependency sync, lint, format check, type check and the
default pytest suite with Postgres and Redis service containers on every push and pull
request. The [manual integration workflow](.github/workflows/integration.yml) runs the same
`pytest -m integration` command against live Nominatim, PVGIS and TCMB without keys; the
real Gemini test inside it skips there, since the workflow sets no key. Run it locally with
`SUNQUOTE_GEMINI_API_KEY` set to include it.

## What comes next

- [Spec #2](https://github.com/tuna-d/sunquote/issues/2) adds an LLM-written Narrative that
  refers to calculated figures through placeholders.
- [Spec #3](https://github.com/tuna-d/sunquote/issues/3) adds a natural-language quote
  assistant and an extraction evaluation suite.

---

Created in [T3 Code](https://t3.codes).
