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

You can provide both `latitude` and `longitude` in `site` to skip Address lookup. The
API uses those Coordinates when both forms are present. For a flat Roof, use
`"roof": {"roof_type": "flat", "usable_area_m2": 40}` to use the configured tilt and
south-facing azimuth. For consumption based on the bill, send `monthly_bill_try` instead
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

Stored Quotes are immutable. The Quote Number sequence restarts each year. API errors use
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
`pytest -m integration` command against live Nominatim, PVGIS and TCMB without keys.

## What comes next

- [Spec #2](https://github.com/tuna-d/sunquote/issues/2) adds an LLM-written Narrative that
  refers to calculated figures through placeholders.
- [Spec #3](https://github.com/tuna-d/sunquote/issues/3) adds a natural-language quote
  assistant and an extraction evaluation suite.

---

Created in [T3 Code](https://t3.codes).
