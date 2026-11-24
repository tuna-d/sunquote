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

`POST /quotes` takes the customer, the site's coordinates, a pitched roof and the monthly
consumption, and returns a quote with one consumption-matched system option (panel count,
`capacity_kwp`, first-year annual and monthly production, and what limited its size). The
production figure comes from [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/) for that
site and roof, so the service needs internet access; no key is needed. Nothing is priced
or stored yet.

```sh
curl -X POST http://localhost:8000/quotes -H 'content-type: application/json' -d '{
  "customer": {"name": "Test Customer"},
  "site": {"latitude": 39.9334, "longitude": 32.8597},
  "roof": {"roof_type": "pitched", "usable_area_m2": 40, "azimuth_deg": 180, "tilt_deg": 30},
  "consumption": {"monthly_consumption_kwh": 500},
  "subscriber_group": "residential"
}'
```

`azimuth_deg` is a compass bearing (180 = south). Errors are `application/problem+json`
(RFC 9457) with a stable `type`, for example `urn:sunquote:problem:no-viable-system`.

## Placeholder data

The panel catalog and the engineering assumptions are TOML files in
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

The `integration` and `eval` markers are excluded from the default `uv run pytest` run.
CI (GitHub Actions) runs lint, format check, type check and the default tests on every
push and pull request. The integration tests (a real PVGIS call) run from a separate
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
