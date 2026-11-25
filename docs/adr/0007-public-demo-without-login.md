# The public demo has no login; abuse is limited by rate limits and an LLM budget

The deployed demo has no sign-in. The write endpoints (`POST /quotes`, the Assistant, MCP) are rate-limited per client IP, and every Gemini call draws from a global daily budget below the free-tier limit; once it is spent, the Narrative uses its fixed text and the Assistant answers `503`. Read endpoints are open. The Quote list is public, seeded with synthetic Quotes, non-seed Quotes are deleted nightly, and the form warns not to enter real personal data.

sunquote serves exactly one Installer, and the demo's audience is an interviewer who should reach a working Quote in one click. A login, even a shared demo password, would put friction exactly there, and real Sales Rep accounts would add a user model the domain does not need. Without any protection, a single script could spend the free Gemini quota for the day and the demo would quietly degrade. Per-browser scoping of the list (an anonymous owner cookie) was rejected because it adds an owner concept to the domain for a demo-only concern.

## Consequences

- Anything typed into the demo is visible to every visitor until the nightly cleanup.
- Rate-limit counters need shared storage across serverless instances: Redis (Upstash) when a free cardless instance is available, otherwise Postgres.
- Real authentication for Sales Reps stays out of scope; adding it later means adding the concept of a user, not changing these limits.
- **When the counter store is down the two limits fail differently, on purpose.** The Gemini budget fails closed: a call whose budget cannot be checked is refused as if the budget were spent (the Narrative uses its fixed text with the `budget_spent` reason, the Assistant answers the budget-exhausted `503`), because the free quota must never be exhausted by the demo. The per-IP rate limiter fails open: a Redis outage must not stop every visitor from creating a Quote, and what it protects (the demo's own capacity) is cheaper to lose than the demo itself.
