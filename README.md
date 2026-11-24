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
push and pull request.

## Layout

```text
src/sunquote/
  domain/     pure calculation engine (no FastAPI, Pydantic, database, network or clock)
  api/        thin FastAPI layer: schemas, validation, error mapping
  adapters/   external sources (irradiance, exchange rate, catalog, persistence)
  config.py   settings read from environment variables
```

A test (`tests/test_architecture.py`) fails if `domain` imports FastAPI, Pydantic, the
`api` or `adapters` layers, or `config`.

---

Created in [T3 Code](https://t3.codes).
