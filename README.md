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
uv run pytest -m eval -rs tests/eval/test_gemini_eval.py
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
- `missing_fields`: when the message lacks something a Quote needs, the assistant asks for all of
  it in one Turkish question (the `reply`) and lists the field paths here (`customer.name`,
  `site.address`, `roof.roof_type`, `roof.tilt_deg`, `roof.azimuth_deg`, `roof.usable_area_m2`,
  `consumption`, `subscriber_group`); otherwise the list is empty.

Answer in a further message, resending the whole conversation, and the Quote is created once
everything is there. When Quote creation fails (Address not found, invalid value, no viable
system, unsupported Subscriber Group, a service unavailable), the reply explains in Turkish what
to change.

The server keeps no conversation: the client sends the whole conversation (1 to 20 messages of
at most 2,000 characters, the last one from `user`) with every request. The model never
supplies Coordinates, since the tool takes only an Address, which is always geocoded. At most one
Quote is created per request and the model is called at most three times, within
`SUNQUOTE_ASSISTANT_TIMEOUT_SECONDS` (30 s) for the model calls and the tools (geocoding, PVGIS,
TCMB, Narrative) together.

With the shipped placeholder catalog the example above gives a Quote with two options. A very
small consumption (for example 300 kWh a month on 40 m²) is too small for any catalog inverter;
the assistant then explains in Turkish that no compatible inverter was found.

**Figures.** As with the Narrative, the model refers to figures through placeholders and the
service fills them ([ADR 0001](docs/adr/0001-llm-never-writes-figures.md)). A reply that breaks
the rules is requested once more. If it breaks them again, or the model fails after the Quote was
created, the reply is a fixed Turkish confirmation with the Quote Number, each option's capacity
and total price, and the document link. When the model is unavailable before any Quote exists,
the endpoint answers `503` with `urn:sunquote:problem:assistant-unavailable`.

A reply without a Quote (a question, an explanation or plain text) may contain digits only as the
Sales Rep wrote them ([ADR 0004](docs/adr/0004-assistant-replies-may-echo-the-sales-reps-digits.md))
and no placeholder syntax; the model is asked again once for each kind of reply (a question, a
text), and then a fixed Turkish reply is used (the missing fields with labels, a generic "the
Quote could not be created" sentence naming the problem, or a request to restate the
information). If the three calls or the time budget run out without a
Quote, the answer is `200` with that request to restate the information and no Quote.

**Privacy.** Unlike the Narrative, the Sales Rep's own messages go to Gemini and may include the
Customer's name and Address. Google's free tier may use submitted content for training.

### Run the extraction eval

Set `SUNQUOTE_GEMINI_API_KEY` in `.env` or the shell, then run from the repository root:

```sh
uv run pytest -m eval -rs tests/eval/test_gemini_extraction_eval.py
```

Use `uv run pytest -m eval -rs` to run both the Narrative and extraction evals. Both are
opt-in, excluded from CI, and skip with a message when the key is unset.

The extraction eval sends [20 synthetic Turkish scenarios](tests/eval/extraction_scenarios.toml)
through the same assistant tool loop used by the endpoint. Only Gemini is contacted. A fake
Quote service records the attempted `create_quote` arguments and returns a canned Quote.
The report shows results per scenario and field. At least 18 of 20 scenarios must pass.
Quote scenarios require one successful tool call with matching fields and no extra arguments.
Addresses are compared after trimming, collapsing whitespace and Turkish lowercasing. Numeric
fields allow a difference of 1% or 0.5, whichever is larger. Question scenarios require exactly
the expected `missing_fields` and no `create_quote` attempt.

Last run on 2026-11-24 with `gemini-3.5-flash-lite`: 19 of 20 scenarios passed (95%). The one
failure asked whether a roof described as "eğimli" was flat or pitched instead of calling
`create_quote`.

`SUNQUOTE_EVAL_DELAY_SECONDS` controls the pause between Gemini requests (15 seconds by default),
including requests within a turn. A call that fails (a rate limit or an outage) is repeated up to
twice after one more pause, so a single HTTP 429 does not fail a scenario. The 20 scenarios contain up to 23 turns with at most three
Gemini calls per turn. Check your project's free-tier limits before running both evals.

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

## Deploy

The API runs for free on [Vercel](https://vercel.com) Hobby as a Python function, with
[Neon](https://neon.com) Postgres and [Upstash](https://upstash.com) Redis. All three have a free
tier that asks for no credit card; if a signup asks for one, stop and use another provider.
Docker Compose is unchanged and stays the local way to run everything.

How the repository maps onto Vercel:

- [`api/index.py`](api/index.py) is the function. It exposes the same FastAPI `app` as
  Compose and defaults two settings for a serverless instance: `SUNQUOTE_DATABASE_CLIENT_POOL=false`
  (every use opens its own connection through Neon's pooler) and
  `SUNQUOTE_MIGRATE_ON_STARTUP=false`. Compose keeps its connection pool and its startup migration.
- [`vercel.json`](vercel.json) sends every path to that function, sets its maximum duration to
  300 seconds (the Hobby limit) and builds only `main`: pull requests get no API preview.
- [`.python-version`](.python-version) pins Python 3.13.
- The [`Migrate production database`](.github/workflows/migrate.yml) workflow runs the
  Alembic migrations (`python -m sunquote.adapters.postgres.migrate`) on every push to `main`.
  Without the `SUNQUOTE_DATABASE_URL` secret it skips with a notice.

### Steps for the repo owner

1. **Neon.** Create a project and copy the *pooled* connection string (the host contains
   `-pooler`). It can be pasted as it is: the app rewrites `postgresql://...?sslmode=require`
   for the asyncpg driver.
2. **Upstash.** Create a Redis database and copy its TLS URL, `rediss://default:<password>@<host>:6379`
   (two `s`).
3. **GitHub.** Add the Neon string as the repository secret `SUNQUOTE_DATABASE_URL`
   (Settings → Secrets and variables → Actions). After the first push to `main`, or by running
   the workflow by hand from the Actions tab, the database is migrated. To migrate from your own
   machine instead: `SUNQUOTE_DATABASE_URL=<neon string> uv run python -m sunquote.adapters.postgres.migrate`.
4. **Vercel.** Import the repository as a new project with the repository root (not `web/`) as
   its root directory, and keep `main` as the production branch. Add the environment variables
   `SUNQUOTE_DATABASE_URL` and `SUNQUOTE_REDIS_URL`, and optionally the free
   `SUNQUOTE_GEMINI_API_KEY`. [`.env.example`](.env.example) lists them all.
5. **Check.** Open `https://<project>.vercel.app/health` and then `/docs`.

Production changes only when `development` is merged into `main`, which is why the migration
runs on pushes to `main` as well.

To run the function entry point locally without a Vercel account, migrate a database and start it
with uvicorn on its own port. This applies the same serverless defaults as Vercel:

```sh
docker compose up -d --wait postgres
uv run python -m sunquote.adapters.postgres.migrate
uv run uvicorn api.index:app --port 8103
```

`vercel dev` (Vercel CLI 48.1.8 or later, after `vercel login`) runs the real Vercel runtime
against the same files. Open `http://localhost:8103/docs` to try the API.

### Nominatim on a serverless host

Every function instance throttles its own Nominatim requests to one per second, and the Redis
cache serves repeated Addresses without calling Nominatim at all. The instances share no lock,
and for demo traffic that is the accepted approach: a cross-instance lock would not be worth its
complexity at a handful of Quotes per hour. If traffic ever outgrows it, point
`SUNQUOTE_NOMINATIM_BASE_URL` at your own instance.

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

## How this was built

sunquote was built with AI agents under a written rulebook. This section says who did what, how a feature went from idea to merged code, how it was reviewed, and which real mistakes were caught along the way. Every claim links to the issue, pull request or commit behind it. Where the record does not show who caught a mistake, the cell says **unconfirmed** and the repo owner has yet to check it.

### Roles

- **Claude does all planning**: grilling sessions, specs, tickets, [GLOSSARY.md](GLOSSARY.md) and the [ADRs](docs/adr). The rule is in [CLAUDE.md](CLAUDE.md) ("Roles: Claude and Codex").
- **Implementation is split by ticket label** ([triage labels](docs/agents/triage-labels.md)). `ready-for-claude` tickets involve design decisions (domain model, money rules, adapters, the API contract) and are built by Claude subagents. `ready-for-codex` tickets are pure execution against a stated spec and are built by GPT subagents under [AGENTS.md](AGENTS.md). `needs-content` tickets (real price lists, tariffs, API keys, final quote copy) belong to the repo owner, and until the owner supplies them the code runs on clearly marked [placeholder data](#placeholder-data).
- **The repo owner** decides, and alone merges `development` into `main` ([CLAUDE.md](CLAUDE.md), "Working on tickets").

### From idea to merged code

1. **Grill.** Claude questions the plan until the decisions are explicit. The vocabulary and the first decision came out of the first design session ([commit a11c443](https://github.com/tuna-d/sunquote/commit/a11c443): GLOSSARY and [ADR 0001](docs/adr/0001-llm-never-writes-figures.md)). The phase 1 grilling session produced ADRs 0005 to 0008 ([PR #28](https://github.com/tuna-d/sunquote/pull/28)).
2. **Spec.** One issue per feature: [#1 Quote engine](https://github.com/tuna-d/sunquote/issues/1), [#2 LLM-written Narrative](https://github.com/tuna-d/sunquote/issues/2), [#3 quote assistant](https://github.com/tuna-d/sunquote/issues/3), and for phase 1 [#29 Web app and live demo](https://github.com/tuna-d/sunquote/issues/29) and [#30 Monthly Netting, Export Price and discounted returns](https://github.com/tuna-d/sunquote/issues/30).
3. **Tickets.** The spec is split into small issues, each with acceptance criteria and a one-line "Why this label". Spec #1 became tickets [#4 to #16](https://github.com/tuna-d/sunquote/issues/4), spec #2 became [#18 to #20](https://github.com/tuna-d/sunquote/issues/18), spec #3 became [#22 to #24](https://github.com/tuna-d/sunquote/issues/22).
4. **`/implement-spec`.** Claude acts as orchestrator: it routes each ticket to a subagent working in its own git worktree, merges the results into one integration branch (`spec/<n>-<slug>`) and opens a single pull request per spec: [#17](https://github.com/tuna-d/sunquote/pull/17) (spec #1), [#21](https://github.com/tuna-d/sunquote/pull/21) (spec #2), [#25](https://github.com/tuna-d/sunquote/pull/25) (spec #3). The rules of the run are in [docs/agents/workflow.md](docs/agents/workflow.md).

### Model and effort routing

The rules are in [docs/agents/workflow.md](docs/agents/workflow.md), "Implementing a spec" (rules 4 to 6):

- `ready-for-codex` tickets go to GPT subagents on `gpt-6.2-sol` by default. `gpt-6.2-astra` needs the repo owner's approval.
- Claude subagents default to Sonnet 5.5, Haiku 5.5 handles light and mechanical work, and Opus needs the repo owner's approval.
- Every subagent gets an explicit effort from a table, never below `medium`: `high` for domain calculations, money, adapters to external services, the API contract, tooling changes and review subagents; `medium` for the rest. A ticket that failed once is retried at `high`.

### How work is reviewed

1. **Codex self-review.** A Codex subagent cannot start subagents, so it reviews its own diff against the ticket and the architecture rules and fixes what it finds ([AGENTS.md](AGENTS.md), "As an implement-spec subagent"). Tickets labelled `needs-claude-review` skip even that and are left to step 2.
2. **Claude code review.** After all tickets of a spec land, the orchestrator runs `code-review` once over the integration branch, covering standards and the spec (`medium` at most, never `ultra`) ([workflow.md](docs/agents/workflow.md), rule 8). The fixes land before the spec's pull request is merged; for spec #1 they are the "[code review fixes](https://github.com/tuna-d/sunquote/commit/5e490e8)" merged into [PR #17](https://github.com/tuna-d/sunquote/pull/17).
3. **CI.** [CI](.github/workflows/ci.yml) runs lint, format check, `mypy` and the default test suite with Postgres and Redis on every push and pull request. The [manual integration workflow](.github/workflows/integration.yml) runs the live-service tests, and the LLM evals run on demand with `pytest -m eval` ([Tests and CI](#tests-and-ci)).
4. **Owner approval.** The repo owner alone decides whether `development` goes into `main` ([PR #27](https://github.com/tuna-d/sunquote/pull/27) is that release).

### Mistakes caught

| # | What went wrong | Who or what caught it | Fix |
|---|---|---|---|
| 1 | The research note's DC/AC maximum of 1.30 left standard small systems without an inverter: a 9-panel 3.96 kWp system fit no inverter (1.32 on 3 kW, 0.99 on 4 kW). | Found while implementing [ticket #7](https://github.com/tuna-d/sunquote/issues/7), per the commit message. **Who exactly: unconfirmed.** | [8c9984e](https://github.com/tuna-d/sunquote/commit/8c9984e): max raised to 1.50, 4 and 6 kW inverters added ([PR #17](https://github.com/tuna-d/sunquote/pull/17) decisions) |
| 2 | Spec #1 used a single Tariff Tier chosen by annual consumption. A Monthly Bill converted to kWh jumped at the threshold (a higher bill could give a lower consumption) and savings near the threshold were mispriced. | Surfaced after the placeholder market research of [ticket #4](https://github.com/tuna-d/sunquote/issues/4), then recorded as an owner decision ([ticket #9 comment](https://github.com/tuna-d/sunquote/issues/9)). **Who first spotted it: unconfirmed.** | [b44e2b0](https://github.com/tuna-d/sunquote/commit/b44e2b0) and [ADR 0002](docs/adr/0002-marginal-tariff-tiers.md): marginal bands |
| 3 | A Quote build that failed (no viable system, no compatible inverter) still used up a Quote Number, leaving gaps in the numbering. | Part of the spec #1 code review fixes ([5e490e8](https://github.com/tuna-d/sunquote/commit/5e490e8)). **Whether a reviewer or a test run found it: unconfirmed.** | [2cecba9](https://github.com/tuna-d/sunquote/commit/2cecba9), with API and domain tests; listed in [PR #17](https://github.com/tuna-d/sunquote/pull/17) |
| 4 | The Contracted Power cap used the Contracted Power itself: with 7 kW and inverters of 6 and 8 kW, the capped Roof-Max system fit no inverter. | Part of the spec #1 code review fixes ([5e490e8](https://github.com/tuna-d/sunquote/commit/5e490e8)). **Who: unconfirmed.** | [0c91bde](https://github.com/tuna-d/sunquote/commit/0c91bde): cap with the largest Catalog inverter within the Contracted Power |
| 5 | The fixed Self-Consumption Ratio of 0.85, derived for a Consumption-Matched system, was applied to Roof-Max too, so a system larger than consumption had its Annual Savings overstated. | The phase 1 grilling session ([PR #28](https://github.com/tuna-d/sunquote/pull/28)). **Who in the session: unconfirmed.** | [ADR 0005](docs/adr/0005-monthly-netting-replaces-self-consumption-ratio.md) in [30b3bb3](https://github.com/tuna-d/sunquote/commit/30b3bb3); the calculation itself is built in [spec #30](https://github.com/tuna-d/sunquote/issues/30) |
| 6 | The live extraction eval passed 15 of 20 scenarios, below the 90% bar: the assistant kept asking for fields a Quote does not need (the tilt and azimuth of a flat roof, the Subscriber Group, the roof type of an "eğimli" roof). | The extraction eval run against real Gemini, as stated in [PR #26](https://github.com/tuna-d/sunquote/pull/26) (follow-up to spec #3). | [d85a6cb](https://github.com/tuna-d/sunquote/commit/d85a6cb): prompt and tool description list the fields that are never missing; the eval then passed 19 of 20 |
| 7 | The README and integration-test example of the assistant used 300 kWh for a 40 m² roof, which has no compatible inverter in the shipped Catalog, so the example would not produce a Quote. | Fixed in the spec #3 review-fix commit [9fd57c1](https://github.com/tuna-d/sunquote/commit/9fd57c1) (the commit message states the cause). **Who or what found it: unconfirmed.** | [9fd57c1](https://github.com/tuna-d/sunquote/commit/9fd57c1): the examples use 500 kWh ([PR #25](https://github.com/tuna-d/sunquote/pull/25)) |

## Status

All three specs are implemented: the [Quote engine](https://github.com/tuna-d/sunquote/issues/1),
the [LLM-written Narrative](https://github.com/tuna-d/sunquote/issues/2) and the
[quote assistant with its extraction eval](https://github.com/tuna-d/sunquote/issues/3). The
domain vocabulary is in [GLOSSARY.md](GLOSSARY.md) and the design decisions are in
[docs/adr](docs/adr). The Catalog, Tariff and pricing inputs remain
[placeholder data](#placeholder-data).

---

Created in [T3 Code](https://t3.codes).
