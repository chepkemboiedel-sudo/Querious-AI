# Querious AI — Roadmap

> **This file gives the direction, not the to-do list.** The [GitHub Project](https://github.com/users/chepkemboiedel-sudo/projects/4) and its Issues are the **authoritative source** for tasks, order (the Sequence field), status, owners and dependencies. If this file and the Project disagree on a task, the Project wins. Then update this file if the direction itself changed.
>
> Technical rules: [ARCHITECTURE.md](ARCHITECTURE.md) · Product and process rules: [POLICY.md](POLICY.md) · Detail: Implementation Plan v1.0 (`docs/plan/`)
>
> Owner: Edel Kiprop · Last reviewed: November 2026

## Where we are

- ✅ **Design.** SDD v1.0 (Final) and the interactive prototype (screens 1–10).
- ✅ **Environment.** AiDev account, branch rulesets (`dev → staging → main`), Project, CLAUDE.md.
- ✅ **Plan.** Implementation Plan v1.0, an AI-drafted backlog of 36 Issues under human review, and these context files.
- ▶ **Next:** Phase 1. Start with the Issues where Phase = P1 and Human Review = Reviewed, in Sequence order.

## Phases

Each phase ends in something you can demo or measure. The Project's **Phase** field uses the names in the first column.

| Phase | Outcome | Main modules | Stories | Done when |
|---|---|---|---|---|
| **P1 Foundation & data** | Load a CSV or the sample and see its tables, columns and business terms. | scaffold, `llm/`, executor (read-only), `semantic/`, `audit/`, screens 1–2 | US-01, US-02, US-12 | A valid CSV loads in under 10 s, bad files are rejected, and a bad term fails at load. |
| **P2 Question pipeline** | A clear question → table + summary + chart. | IR, planner, validator, compiler, executor, explainer, question API, screens 3, 5, 6 | US-03 | A gold-set question is answered from an executed query, and the same plan gives the same SQL. |
| **P3 Clarify & correct** | Ask instead of guessing, fix errors visibly, fail honestly. | ambiguity check, base checks, correction loop, screens 4 and 8 | US-04, US-06, US-07 | Ambiguous questions are clarified first, an injected error is fixed within 3 attempts, and unsupported questions show no number. |
| **P4 Trust & verification** | Every answer shows its risk, checks, verification support and provenance. | risk classifier, check registry, trust policy, provenance, screen 7 | US-05, US-11 | Fixtures give the exact RC-17 level, and a failed join check blocks the answer. |
| **P5 Audit & history** | Reopen, replay, rate and follow up. | full audit record, replay, history, feedback, follow-ups, screens 9–10 | US-08, US-09, US-10 | History survives a restart and replay matches the audit. |
| **P6 Evaluation & hardening** | Measured MVP. | gold set, `eval/` harness, accessibility and acceptance pass | US-13 (US-14 optional) | One command produces the report, and US-01 to US-13 checks are passing or documented. |

Phases are ordered by shared contracts: IR, semantic layer and audit events come first. Parallel work is fine inside the limits set by each Issue's "blocked by" links.

## Milestones

1. **MVP demo:** P1–P5 merged to `dev`, then promoted to `staging` by the owner.
2. **Evaluated MVP:** P6 report published and promoted to `main` as a release.
3. **Research option:** US-14 baseline comparison (TMP-36), only after the evaluated MVP.

## Not on the roadmap

- **Future work:** FUT-01, a pinned-answer board. It needs a new story, a new screen and an SDD change first.
- **Non-goals (SDD 2.3):** writing data, autonomous multi-step agents, arbitrary SQL, cloud or production databases, accounts and sharing, a semantic-layer editor, forecasting or ML, dashboards and BI export, fine-tuning.

## Keeping this file current

Update it when a phase finishes, when phase scope changes (with an ADR or an owner decision), or when a milestone moves. Don't copy Issue lists or statuses here. Link to the Project instead.
