# sunquote web

The Sales Rep's web app: Next.js (App Router), TypeScript `strict`, npm, Node 24 LTS
(`.nvmrc`, `engines`). Turkish UI. It shows what the API returns and **never computes a
figure**; `Intl` with `tr-TR` formats only values the API gives raw (`src/lib/format.ts`).

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server on port 3000 (`npm run dev -- --port 3101` for another). |
| `npm run lint` / `npm run typecheck` / `npm test` | ESLint, `tsc --noEmit`, Vitest. |
| `npm run build` | Production build (downloads the Google fonts, so it needs internet). |
| `npm run e2e` | The Playwright smoke test (`e2e/`): the web app in dev mode against a mocked API (`e2e/mock-api.mjs`). Needs `npx playwright install chromium` once. `E2E_WEB_PORT` / `E2E_API_PORT` move its two ports (defaults 3210 / 8210). |
| `npm run api:sync` | Re-export the API's OpenAPI schema to `openapi.json` and regenerate `src/api/schema.d.ts`. Run it after any API schema change and commit both files; the CI web job fails on a diff. |

Set `SUNQUOTE_API_URL` (default `http://localhost:8000`) to point at the API. Next reads it at
build time as well, because the `/api/:path*` rewrite in `next.config.ts` is baked in.

## What later page tickets build on

- **Layout and tokens.** `src/app/layout.tsx` (skip link, masthead, `<main id="main">`, the
  Newsreader and Hanken Grotesk fonts through `next/font/google`) and `src/app/globals.css`
  (the colour, type and spacing tokens as CSS variables, plus the shared classes: `.sheet`,
  `.letter`, `.kick`, `.sub`, `.lede`, `.meta`, `.btn` / `.btn.ghost`, `table.t`, `.sr`). Use
  the variables; write a component's own styles as a CSS module next to it
  (`QuoteListView.module.css` is the model). The reference is
  [`docs/design/2c-slate-sun.html`](../docs/design/2c-slate-sun.html) (it also has the form
  markup for #45) and the token rules are in
  [`docs/design/tokens-2c.md`](../docs/design/tokens-2c.md). Gold is a fill behind ink text,
  never text, a line or a chart series. No component library theme; Radix unstyled primitives
  are fine.
- **Masthead sections.** `src/lib/navigation.ts` lists them. `Yeni teklif` is enabled (#45);
  `Asistan` is `enabled: false` (shown struck through, not linked) until its route exists: flip
  the flag in #46.
- **Shared by the form and the Assistant.** `src/components/demo-banner.tsx` is the public-demo
  warning: put it above the fields. `src/api/problem.ts` reads `application/problem+json`:
  `problemFrom(error, response)` on what the typed client returns, `PROBLEM_TYPES` for the
  `urn:sunquote:problem:*` types and `parseRetryAfter` for a 429's wait (`formatWait` in
  `src/lib/format.ts` writes it in Turkish). The form's own rules (the API's bounds, the request,
  the failure messages) are in `src/lib/quote-form.ts`.
- **API client.** `src/api/client.ts` makes the typed `openapi-fetch` client over the
  generated `src/api/schema.d.ts`. In the browser its base URL is `/api` (the rewrite); on the
  server it is `SUNQUOTE_API_URL`. `src/api/types.ts` names the schemas
  (`QuoteListItem`, ...): add the ones you need. `src/api/quotes.ts` is the model for a data
  loader: it never throws and returns `{ ok: true, ... } | { ok: false, reason }`, so the page
  renders the failure.
- **Page pattern.** A page is a thin async server component: read the params, call the loader,
  render a pure view (`QuoteListView`). The view is what the tests render.
- **Formatting.** `src/lib/format.ts` (`formatTry`, `formatCapacityKwp`, `formatCreatedAt`, ...)
  uses non-breaking spaces and Istanbul time. Add new formatters there, with tests.

## Tests

Vitest with Testing Library and jsdom (`vitest.config.mts`, `test/setup.ts`; jest-dom matchers
are loaded). Tests sit next to the code (`*.test.ts(x)`). They drive the public surface:
render the view and assert what the Sales Rep reads, or call a helper. API loaders are tested
with a fake `fetch` passed to `createApiClient` (see `src/api/quotes.test.ts`); no test calls
the network. `next/navigation` is mocked where a component needs the router
(`MainNav.test.tsx`). The form's tests (`QuoteForm.test.tsx`) pass a client over a fake `fetch` and mock the router.
The Playwright smoke test lives in `e2e/` with its own CI step in `.github/workflows/ci.yml`; a
page ticket that needs another mocked route adds it to `e2e/mock-api.mjs`.
