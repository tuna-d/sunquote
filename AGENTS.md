# Agent instructions (Codex and other non-Claude agents)

`CLAUDE.md` is the project rulebook: read it before starting. Where it conflicts with
this file, `CLAUDE.md` wins. For finishing a ticket, follow "Finishing a ticket" below,
not the Claude-only steps in `docs/agents/workflow.md`.

Reach for the other docs when the ticket needs them: `docs/utils/` for product notes,
sample quotes and price lists (local only, gitignored), `GLOSSARY.md` for names in code
and PR text, `CODING_STANDARDS.md` (once it exists) for code style, `docs/agents/` for
the issue tracker and labels.

## Your role

You implement tickets labelled `ready-for-codex`. If a ticket is labelled
`ready-for-claude` or has no role label, stop and say so. If a `ready-for-codex`
ticket needs a design decision it does not cover, stop and say what is missing.
When implementing a spec as a subagent, follow "As an implement-spec subagent" below.

## Working on a ticket

1. Read the issue (`gh issue view <number> --repo tuna-d/sunquote`) and any spec it
   links to.
2. Branch off the latest `development` (this form also works in a worktree):

       git fetch origin
       git checkout -b ticket/<issue-number>-<short-slug> origin/development

3. Run `uv sync`. Use TDD by default (`/tdd` if the skill is installed): write a failing
   test, make it pass, then refactor while keeping tests green. Writing and running the
   required tests is part of the authorized ticket work; proceed without asking the
   owner whether to write or run them.
4. Before opening the PR, run `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run mypy src` and `uv run pytest`, and report the results honestly. Run
   `uv run pytest -m integration` only when the ticket touches an adapter and the
   needed keys are set; otherwise say it did not run. If you start a dev server, use a
   port of your own, not 8000, since other worktrees may be running.
5. For API changes, put an example request and response for each changed endpoint in
   the PR description.
6. Commit to the ticket branch only and open the PR against `development`, referencing
   the issue.

## Finishing a ticket

Once the PR is open, follow these steps in order:

1. Always write a short summary **in Turkish**: what changed and where, notable
   decisions and trade-offs, open points, and the actual test results (including
   failures or tests that could not run). Keep `GLOSSARY.md` terms in English inside
   Turkish sentences. Include the PR link.
2. Run a code review on the PR (`/code-review medium` at most, never `ultra`), fix what
   it raises, and rerun the tests. Mention the review outcome in the summary.
3. If the ticket has `needs-claude-review`, do not merge and do not close the issue.
   Say in the summary that the label is set, give the branch, the endpoints and tests to
   verify, and stop. The owner has Claude review the PR and merges it.
4. Otherwise, merge the PR into `development` without asking. After confirming the
   merge succeeded, close its issue with `gh issue close <number> --repo tuna-d/sunquote`,
   and tell the owner it is merged. Never merge into `main`.

Wait for the owner's instruction before starting the next ticket.

If the owner reports a problem, fix it on the same ticket branch, rerun the relevant
tests, update the PR and repeat the steps above.

## As an implement-spec subagent

When the brief says you are a subagent of `/implement-spec`, the orchestrator (Claude)
owns branches, PRs, merges and issue closing. You build one ticket:

1. Work in your worktree on its temporary branch, based on the integration branch the
   brief names. Merge the integration branch tip into your branch before reporting done.
2. Run `uv sync`. Use TDD. Use the port the brief gives you for any dev server. Run
   ruff, mypy and the pytest modules your ticket touches; the orchestrator runs the full
   suite.
3. Skip "Finishing a ticket": open no PR, merge nothing, close no issue.
4. Review: if the ticket has `needs-claude-review`, skip it. Otherwise review your own
   diff against the ticket, the architecture rules in `CLAUDE.md` and
   `CODING_STANDARDS.md` (if present), and fix what you find; you cannot start the
   subagents `/code-review` needs.
5. Report in your final message: what changed and where, decisions, open points, the
   actual test results (including failures or tests that could not run).
6. Stuck (spec gap, ADR conflict, test red after two attempts, design choice with
   several reasonable answers, missing price data, tariff or API key): stop and say
   what is missing.

## Scope

- Do only what the ticket asks. Anything out of scope that you notice goes into the
  PR description as a note.
- Never invent real-world figures (equipment prices, exchange rates, tariffs, tax rates,
  irradiance values, company details) or final customer-facing copy. Use clearly marked
  placeholders in the data files and say so in the summary.
- Edit `CLAUDE.md`, `AGENTS.md`, `CODING_STANDARDS.md` or ADRs only when the ticket asks.
