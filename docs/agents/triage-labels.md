# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker  | Meaning                                  |
| -------------------------- | --------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`        | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`          | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-claude`    | Fully specified, but the builder must make design decisions: Claude implements |
| `ready-for-agent`          | `ready-for-codex`     | Fully specified, execution only: Codex implements |
| _(project-specific)_       | `needs-claude-review` | Only on `ready-for-codex` tickets: the orchestrator's `code-review` covers the ticket and its subagent skips its own review |
| `ready-for-human`          | `ready-for-human`     | Requires human implementation            |
| _(project-specific)_       | `needs-content`       | Real price lists, datasheets, tariffs, company details, API keys or final quote copy: the repo owner provides them, no agent builds it |
| `wontfix`                  | `wontfix`             | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

## Choosing the builder label

When writing a ticket (`to-tickets`), Claude picks the label by asking: will whoever
builds this have to make design decisions, or only carry out a spec?

- `ready-for-codex`: the work is execution. The ticket already states the acceptance
  criteria, the files to touch and the expected behaviour. Examples: an endpoint that
  wires an existing domain function to the API, request/response schemas fully given
  in the ticket, a data file in an existing format, a quote template from a given
  layout, adding tests around existing logic, a calculation whose formula and worked
  example are spelled out in the ticket.
- `ready-for-claude`: the builder has to decide something. Examples: the domain model
  and its types, money/currency and rounding rules, sizing and production-estimate
  logic, pricing and financial analysis, adapter design for external services, the API
  contract and error model, project and tooling setup, work spanning several modules,
  any ticket whose spec has gaps.
- When unsure, label it `ready-for-claude`. Fixing a hard ticket that went to Codex
  costs more than doing an easy one in Claude.

A ticket that needs data only the owner can provide (real price lists, datasheets,
tariffs, company details, API keys, final quote copy) gets `needs-content` instead of a
builder label. `to-tickets` puts these tickets last, so the repo owner can gather the
data in the background while the orchestrator builds the rest with placeholders.
Tickets that cannot be built even with placeholders are blocked by the `needs-content`
ticket.

Every ticket gets one line, "Why this label", giving the reason for its label.

Every bullet of the spec's Implementation Decisions lands in some ticket's acceptance
criteria, chores included (a dependency bump, a doc to update, a placeholder to remove);
a decision with no ticket is never built.

Claude adds `needs-claude-review` only to `ready-for-codex` tickets whose PR deserves
a Claude review: changes to `domain` calculations or money handling, adapters, the API
contract, work spanning several modules, and anything hard to reverse (`pyproject.toml`,
tooling configuration, dependency changes). A `ready-for-claude` ticket never gets it,
since Claude builds that one itself. Codex tickets without it review their own diff
with `/code-review medium`. Use `medium` at most; never `ultra`.

Edit the right-hand column to match whatever vocabulary you actually use.
