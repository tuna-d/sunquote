<img src="assets/icon.svg" width="64" height="64" alt="">

# sunquote

A backend service that prepares a customer-ready rooftop solar (PV) quote for a Turkish
installer. Input: the site's location, the roof (area, orientation, tilt) and the
customer's electricity consumption or bill. Output: system size (kWp), panel and inverter
choice, yearly production estimate, cost and sale price, savings and payback period.

This is a portfolio project. It works with clearly marked placeholder data (catalog,
prices, tariffs), each value with its source and date, not with a real company's data.

Stack: Python 3.13, FastAPI, Pydantic, [uv](https://docs.astral.sh/uv/).

## Run with Docker Compose

```sh
docker compose up --build
```

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

No API keys are needed. To publish on another host port, set `API_HOST_PORT`:

```sh
API_HOST_PORT=8080 docker compose up --build
```

All variables are documented in [`.env.example`](.env.example). Copy it to `.env` to
override a default; every variable is optional.

## Run locally

```sh
uv sync
uv run fastapi dev src/sunquote/api/app.py --port 8000
```

## Create a quote

`POST /quotes` takes the customer, the site's coordinates, a pitched or flat roof and the monthly
consumption, and returns a quote with one consumption-matched system option (panel count,
`capacity_kwp`, first-year annual and monthly production, what limited its size, the chosen
inverter, and its price: Installation Cost, Sale Price, VAT and total in whole lira). The
production figure comes from [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/) for that
site and roof. Equipment prices are USD and are converted to TRY with the USD forex selling
rate that the central bank ([TCMB](https://www.tcmb.gov.tr/kurlar/kurlar_tr.html)) published
on the last business day before the quote date. The service needs internet access; no key is
needed. The Quote is stored (see below).

```sh
curl -X POST http://localhost:8000/quotes -H 'content-type: application/json' -d '{
  "customer": {"name": "Test Customer"},
  "site": {"latitude": 39.9334, "longitude": 32.8597},
  "roof": {"roof_type": "pitched", "usable_area_m2": 40, "azimuth_deg": 180, "tilt_deg": 30},
  "consumption": {"monthly_consumption_kwh": 500},
  "subscriber_group": "residential"
}'
```

For a pitched roof, give `tilt_deg` and the compass bearing `azimuth_deg` (180 = south).
For a flat roof, send `"roof": {"roof_type": "flat", "usable_area_m2": 40}`.
Flat roofs use the configured tilt and a south-facing azimuth. The Quote records the effective
angles and the Coverage Ratio for that Roof Type in its Assumptions.

To price with your own rate (and skip TCMB), add
`"exchange_rate_override": {"rate": 45.5, "date": "2026-11-20"}` (TRY per USD); the quote
records that the rate was overridden.

Errors are `application/problem+json` (RFC 9457) with a stable `type`, for example
`urn:sunquote:problem:no-viable-system`.

## Stored quotes

Every created Quote is stored in Postgres and never changes afterwards. It gets a UUID and a
Quote Number like `SQ-2026-000123` (the sequence restarts each year), and a valid-until date:
the quote date plus the Validity Period (15 days, from the placeholder assumptions).

- `GET /quotes/{id}` returns the stored Quote, or a 404 problem.
- `GET /quotes?page=1&page_size=20` lists Quotes, newest first, with the Customer name,
  the number of System Options, and the first option's `capacity_kwp` and total price.
  `district` and `province` stay null until address geocoding exists.

A request that fails with 422 or 503 stores nothing. A Quote Number is taken just before the
calculation, so a request that then finds no viable system or no compatible inverter leaves a
gap in the numbers.

Persistence is async SQLAlchemy 2.0 with asyncpg. The schema is managed with Alembic; the API
applies the migrations when it starts (turn that off with `SUNQUOTE_MIGRATE_ON_STARTUP=false`).
To run the API outside Compose, start the database with `docker compose up postgres` first.

## Placeholder data

The catalog (panels and inverters, with USD unit prices) and the engineering and pricing
assumptions (DC/AC range, BOS, labour, fixed project cost, Margin, VAT) are TOML files in
[`src/sunquote/data/`](src/sunquote/data). They are placeholders: every value names its
kind (direct, derived or estimate), its source and its date, taken from
[`docs/research/placeholder-market-data.md`](docs/research/placeholder-market-data.md).
Set `SUNQUOTE_DATA_DIR` to load your own files instead.

## Tests and checks

```sh
uv run pytest                  # unit tests; offline, fast (default run)
uv run pytest -m integration   # tests against real external services (run by hand)
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The Postgres repository tests need a database. Start one with `docker compose up postgres`,
then run `SUNQUOTE_TEST_DATABASE_URL=postgresql+asyncpg://sunquote:sunquote@localhost:5432/sunquote
uv run pytest`. Without that variable they are skipped. Each test works in its own temporary
schema.

The `integration` and `eval` markers are excluded from the default `uv run pytest` run.
CI (GitHub Actions) runs lint, format check, type check and the default tests on every
push and pull request, with a Postgres service container for the repository tests. The integration tests (real PVGIS and TCMB calls) run from a separate
workflow that is started by hand from the Actions tab.

## Layout

```text
src/sunquote/
  domain/     pure calculation engine (no FastAPI, Pydantic, database, network or clock)
  api/        thin FastAPI layer: schemas, validation, error mapping
  adapters/   external sources (irradiance, exchange rate, catalog, persistence)
  data/       placeholder catalog and assumptions (TOML)
  bootstrap.py  wires the real adapters (the composition root)
  config.py   settings read from environment variables
```

A test (`tests/test_architecture.py`) fails if `domain` imports FastAPI, Pydantic, the
`api` or `adapters` layers, or `config`.

---

Created in [T3 Code](https://t3.codes).
