# Ticket workflow

How Claude finishes a ticket, handles a Codex PR, and runs `/implement-spec`. Branch
and merge-approval basics are in `CLAUDE.md` ("Working on tickets").

## When a ticket is done

For a ticket Claude implemented, once the PR is open:

1. **Summary.** Write the repo owner a summary in Turkish of what was done for the
   ticket: what changed, where, and anything notable (decisions, trade-offs, open
   points), with the PR link. Never skip it.
2. **Merge and close.** Don't ask a merge question. Merge the PR into `development`,
   then close the ticket's issue with `gh issue close <number>`. Merging into
   `development` does not close the issue by itself, since GitHub only auto-closes on
   merges into the default branch. Tell the repo owner once it is merged.

## After reviewing a Codex PR

For a Codex PR, Codex writes the Turkish summary and stops; the repo owner then tests
it, or asks Claude to review it when the ticket has `needs-claude-review`. After that
review, ask the merge question with `AskUserQuestion`: one question with exactly these
three options, so they pick one instead of typing an answer:

1. **Merge and close the issue.** Merge the PR into `development`, then close the
   ticket's issue with `gh issue close <number>`, as above.
2. **I'll test it first.** The repo owner checks out the branch, runs `uv sync` and
   `uv run fastapi dev src/sunquote/api/app.py`, and tries the endpoints on
   `http://localhost:8000/docs`. Give them the branch name, the endpoints to call and a
   ready-to-paste example request body for each. Then show an interactive checklist
   with `show_widget` (load it with `read_me` first). List the concrete things to check
   for this ticket, taken from its acceptance criteria and what the change touches
   (expected figures in the quote, validation errors for bad input), one checkbox each.
   When every box is ticked, the widget calls `sendPrompt` with a message saying all
   checks passed, and that message is the go-ahead: merge the PR and close the issue as
   in option 1. Until then, do nothing. If the owner reports a problem instead, fix it
   on the same branch and ask the three-option question again.
3. **I'll merge it myself.** Do nothing more for this ticket, not merge, not close, not
   follow up, until the repo owner gives a new instruction.

## Implementing a spec

When running `/implement-spec`, Claude is the orchestrator and every ticket of the spec
is built in this one run: Claude subagents for `ready-for-claude`, GPT subagents for
`ready-for-codex`. These rules apply on top of the skill:

1. **Routing.** The ticket's label picks the builder:
   - `ready-for-claude`: Claude subagent (Agent tool, rule 5).
   - `ready-for-codex`: Codex subagent (`delegate_task`, rule 4).
   - `needs-content`: the repo owner. Never delegate it. List these tickets in the final
     summary.
2. **Branches.** The integration branch is `spec/<spec-issue-number>-<short-slug>`, cut
   from `development`. It replaces per-ticket `ticket/...` branches and PRs. Subagents
   work in worktrees on temporary branches, never open PRs, and the worktrees are
   deleted at the end.
3. **Content blockers.** Keep working every ticket that is not blocked; build with
   clearly marked placeholder data (prices, rates, tariffs) where the real data is not
   in yet. A ticket blocked by an open `needs-content` ticket stays waiting; name it and
   its content blocker in the final summary. `to-tickets` puts `needs-content` tickets
   last, so the owner can gather the data in the background.
4. **Codex subagents.** Call `orchestrator_capabilities` once, before the first
   `delegate_task`. Start each with `target: {providerInstanceId: "codex", model,
   options: {reasoningEffort}}` (effort from rule 6) and `isolation: "worktree"`. The
   child gets no history: the brief holds pointers only (ticket and spec issue numbers,
   the integration branch, its port from rule 7, and "follow `AGENTS.md`, section 'As an
   implement-spec subagent'"). Choose the model by ticket. Only `gpt-6.2-sol` and
   `gpt-6.2-astra` are used; never a `gpt-6.1-*` or older model, not even for easy
   tickets:
   - `gpt-6.2-sol`: default, including very easy, mechanical tickets.
   - `gpt-6.2-astra`: only with the repo owner's approval. Before starting, list the
     tickets that need it with a one-sentence reason each and wait. Ask again before
     moving a ticket to `gpt-6.2-astra` after it fails twice on `gpt-6.2-sol`.
5. **Claude subagents.** Give each the cheapest model that can do its job safely:
   - Light work (exploration, mechanical well-specified tickets, merges): Haiku 5.5
     (Agent tool `model: "haiku"`).
   - Default for implementers and review fixes: Sonnet 5.5.
   - Opus only with the repo owner's approval, asked the same way as `gpt-6.2-astra`.
6. **Subagent effort.** Every subagent gets an explicit effort from this table, set on
   the call (Agent tool `effort`, Codex `options.reasoningEffort`). It never depends on
   the orchestrator's own effort. Take the first row that matches:

   | Condition | Effort |
   |---|---|
   | Retry of a ticket that failed once | `high` |
   | Ticket changes `domain` calculations (sizing, production estimate, pricing, money and currency, financial analysis) | `high` |
   | Ticket changes an adapter to an external service, or the API contract (request/response schemas, error model) | `high` |
   | Ticket changes `pyproject.toml`, tooling configuration, or adds a dependency | `high` |
   | Review subagents of `/code-review` (Standards, Spec) | `high` |
   | Any subagent on Opus or `gpt-6.2-astra` | `high` |
   | Everything else (endpoint wiring, quote templates, data files, tests around existing logic, docs, review fixes, merges, conflict resolution, mechanical tickets, exploration) | `medium` |

   - Effort is never below `medium`, and never `xhigh` or `max`.
   - The ticket's scope comes from the files it is expected to touch. When unsure, take
     `high`.
   - The orchestrator may raise a `medium` row to `high` when the ticket is genuinely
     hard despite its scope (tricky rounding or currency edge cases, several interacting
     modules, an unclear bug). Write the reason in one sentence in the brief and repeat
     it in the final summary. It never lowers a `high` row to `medium`.
   - After a ticket fails twice at `high`, never raise effort further. Move it to a
     stronger model under the approval rules of rules 4 and 5.
7. **Worktrees and tests.**
   - Run at most five worktrees at once, so the providers' rate limits hold. Start the
     next ticket when one lands.
   - Each worktree runs `uv sync` (the uv cache is shared, so this is quick).
   - Every brief gives the subagent its own dev server port (8101, 8102, ... by slot);
     8000 stays free for the owner.
   - A subagent runs ruff, mypy and the pytest modules its ticket touches.
   - After each merge, the orchestrator runs `uv run mypy src` and the full
     `uv run pytest` in the integration branch's worktree in the background, so a ticket
     that breaks another module is found while the next tickets build. After every
     ticket has landed, it runs `uv run ruff check .`, `uv run ruff format --check .`,
     `uv run mypy src` and `uv run pytest` there once, plus `uv run pytest -m
     integration` when the keys are available, and reports the actual result.
8. **Review.**
   - A Codex subagent cannot start subagents, so it cannot run `/code-review`: it reviews
     its own diff against the ticket and fixes what it finds.
   - A `ready-for-codex` ticket with `needs-claude-review`: its subagent skips even that.
   - After all tickets land, the orchestrator runs the skill's `code-review` once over the
     integration branch (`medium` at most, never `ultra`). That review covers the
     `needs-claude-review` tickets.
9. **Getting stuck.** Don't guess. If a subagent hits a gap or contradiction in the
   spec, a conflict with an ADR, a test that stays red after two attempts, a missing
   real-world figure, or a design choice with more than one reasonable answer, ask the
   repo owner, naming the ticket and the options briefly. Unrelated tickets keep going
   meanwhile.
10. **Finishing.** Open one PR from the integration branch into `development` that lists
    the spec issue and every ticket it implements. After the code review, merge it
    without asking, then close the implemented tickets with `gh issue close`, and the
    spec issue too unless a `needs-content` ticket or a blocked ticket of the spec is
    still open.
11. **Summary.** End with one short Turkish summary as bullet points: what each ticket
    did, decisions, open points, the `needs-content` tickets left for the repo owner,
    which placeholder data is still in use, and the actual test results. Keep it brief.
