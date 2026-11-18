# Querious AI — Operating Guide for Claude Code

Querious answers plain-English questions about a user's data and shows how each answer was found. Core idea: **the AI suggests, the system checks.** This file is the always-on guide for every session. Details live in the files linked below; read them when the trigger applies, don't copy them here.

---

## 1. Hard rules (do not break; changing one needs a human-approved ADR, §9)

| ID | Rule | Source |
| --- | --- | --- |
| H1 | The LLM is used for exactly two jobs: checking whether a question is ambiguous, and drafting a query plan. It never executes queries, never produces the SQL that runs, and never writes user-facing explanations. | DD-01, RC-02 |
| H2 | The query plan is a JSON object validated by the Pydantic schema in the pipeline package. SQL is compiled from a validated plan by deterministic code (SQLGlot). Never execute SQL text that came from a model. | DD-02 |
| H3 | Data access is read-only. Each attempt runs one compiled `SELECT`, with a 15-second timeout and a 5,000-row limit. Deterministic helper `SELECT`s for checks and provenance (RC-23) are allowed only through the same safety gate and limits. No `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP` or `ALTER`, ever. | RC-01, RC-23 |
| H4 | Only schema metadata (table/column names and types), semantic-layer definitions, the user's question, and error messages with literal values removed may be sent to the LLM. Row values, sample rows and query results are never sent. | RC-07 |
| H5 | Every number shown to a user comes from an executed query result. If a question cannot be answered, show the reason and what was tried, and no number. | RC-03 |
| H6 | Self-correction is triggered only by concrete signals: schema validation errors, database errors or failed result checks. At most 3 attempts per question. Never ask the model to judge its own answer. | DD-05, RC-04 |
| H7 | If a question has more than one reasonable meaning, ask the user to choose before anything runs. | DD-06, RC-20 |
| H8 | Business terms, metrics and allowed joins come only from `semantic_layer.yaml`. A plan that uses an undeclared join or term is rejected by the validator. | DD-03, RC-05 |
| H9 | Explanations ("How I read your question", the plain-English plan) are generated from the validated plan and the actual results using templates. | DD-04, RC-13 |
| H10 | Every attempt, including failed ones, is written to the SQLite audit log with its plan, error and checks. Provenance and the correction replay are read from the audit log, never reconstructed by a model. | DD-10, RC-22 |
| H11 | Verification support (High / Medium / Low) comes from the fixed RC-17 policy and its listed reasons, never from model confidence or a model-generated score. | DD-08, RC-17 |
| H12 | The MVP is local and single-user: embedded DuckDB and SQLite, no hosted database, no user accounts. | DD-07 |
| H13 | All model calls go through the LLM provider interface. No other module imports a model SDK directly. | SDD 5.1 |
| H14 | The direct LLM-to-SQL baseline (US-14) lives only in the developer evaluation runner. It is never reachable from the user-facing app. This runner is the only documented exception to H2: it may execute model SQL, only after a single-SELECT allowlist check, read-only, against a disposable copy of the evaluation data. | DD-11, RC-23 |

Every hard rule needs at least one automated test. Required tests:

- H3: compiled SQL is a single read-only `SELECT`; anything else is rejected before execution.
- H4: the payload sent to the LLM provider contains no row values.
- H5: a failed or empty pipeline run returns no numeric answer.
- H6: the correction loop stops after 3 attempts and logs each one.

## 2. Sources and when to read them

| Read | When |
| --- | --- |
| `docs/ARCHITECTURE.md` | Before touching module boundaries, imports, 🔒 contracts (IR, semantic-layer format, audit events, provider interface, policy versions (risk policy, trust policy, check registry)), tech choices or the repo layout (§11). |
| `docs/POLICY.md` | Before changing UI text, terminology, data/privacy handling or the work process, and whenever an open decision (OD-x) comes up. |
| `docs/plan/implementation-plan.md` | For phase context, sequencing and agent guardrails (§3, §4, §6). Prototype link: §1.2. |
| `docs/ROADMAP.md` | For direction and phase outcomes. It is never a task. |
| `docs/backlog-map.md` | To map a TMP ID to its Issue number. |
| `docs/design/` (SDD PDF) | When the files above don't answer a design question. The SDD wins over the prototype. |
| **Don't read unless asked** | `docs/backlog-proposal.md`, `docs/aidev-log.md`. |

## 3. Task intent

- The only source of task intent is an Issue in [GitHub Project 4](https://github.com/users/chepkemboiedel-sudo/projects/4) with **Status = Ready**, **Human Review = Reviewed** and **Executor = AI Dev or Pair**. Never take Executor = Human.
- The Project field **Human Review** is authoritative. Ignore any "Human Review: Pending" footer in Issue bodies, and do not edit those footers.
- For **Pair** Issues, stop and ask (§8) at each decision point the Issue names, for example thresholds or gold-set labels.
- Scope is the Issue's acceptance criteria and non-goals. Nothing more.
- Exception: configuration and documentation work (`CLAUDE.md`, `.claude/**`, `docs/**`) may run on a `chore/*` or `docs/*` branch without an Issue.

## 4. Commands (expected; confirm after #3)

```powershell
# Backend, from backend/. Default "python" on this machine is 3.15; the project needs 3.12.
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pytest                              # mock LLM provider only; no network (AR-11)
uvicorn app.main:app --reload       # GET /health -> {"status": "ok"}

# Frontend, from frontend/ (Node 22 LTS)
npm ci
npm run dev
npm test
npm run build
```

- CI runs backend and frontend tests and the H12/H13/H14 import scan. The scan command is defined by #3.
- Use pip with `requirements*.txt` only (no uv).
- Candidate future improvements (not in #3): linters, formatters and type checkers; a `.gitattributes` for line endings.

## 5. Branches, pull requests and Project status

- **Branches:** `main` ← `staging` ← `dev` ← work branches `feature/*`, `fix/*`, `docs/*`, `chore/*`. Always branch from `dev`.
- Never push to `staging` or `main`. Only the owner opens and merges `dev → staging` and `staging → main` PRs; AiDev never opens PRs into `staging` or `main`.
- **One Issue per PR** into `dev`, with `Closes #<n>` in the description.
- **Commits:** `type: short summary`, where type is `feat`, `fix`, `docs`, `test`, `refactor` or `chore`.
- **Self-merge into `dev`** is allowed when the checks pass, except in the cases below. Until CI exists, "checks pass" means the relevant tests pass locally and the command output is pasted in the PR.
- **No self-merge; wait for owner approval on GitHub (chepkemboiedel-sudo):**
  - **#3** (scaffold and CI): its own CI run must pass **and** the owner must approve before merge.
  - **Contract PRs #8, #14, #16, #17** (IR schema, provider interface, semantic-layer format, audit event model).
  - Any PR that changes `CLAUDE.md`, `.claude/**`, `docs/ARCHITECTURE.md` or `docs/POLICY.md`.
- **Project Status** (exact names). You move:
  - Ready → **In progress** when you start;
  - → **Agent review** when the PR is open;
  - → **Done in Dev** right after you merge into `dev`.

  **Staging Candidate** and **Released** belong to the owner. Never move anything to **Ready**, and never set Human Review.

## 6. Definition of Done and PR evidence

A PR into `dev` is done when:

1. Every acceptance criterion in its Issue is met and checked off.
2. New behaviour has tests, and all tests pass, in CI or locally per §5.
3. No hard rule is broken, and every hard rule it touches has a test.
4. The PR description contains:
   - `Closes #n`;
   - what changed;
   - each AC mapped to the test or file that shows it;
   - test evidence: the `test-evidence-runner` summary (verdict ALL PASS), plus a CI link once CI exists;
   - the `guardrail-reviewer` verdict (PASS) and its AC → evidence table;
   - the hard rules touched and their tests;
   - SDD references (US / RC / DD IDs);
   - the docs updated.

## 7. Documentation

- When the repo layout changes, update `docs/ARCHITECTURE.md` §11 in the same PR.
- When run commands change, update the README and §4 here.
- 🔒 contracts and hard rules change only through an ADR (§9). Update ROADMAP only when a phase or milestone changes.
- Never copy Issue lists or statuses into docs. Link to the Project instead.

## 8. Decide alone vs. stop and ask

**Decide alone, within the Issue's scope:**
- internal structure and naming inside a package, and test design;
- refactors local to the Issue;
- message wording that follows POLICY terminology;
- UI layout and styling that matches the prototype;
- which checks go in the verification registry (subject to the OD-5 thresholds). Adding or changing a check within an Issue's scope bumps the registry version; changing the shape of the policy-versions contract still needs stop-and-ask and an ADR;
- versions of dependencies already in use.

**Stop and ask before you:**
- change or work around any hard rule (H1–H14), or a 🔒 contract (IR, semantic-layer format, audit-event format, provider interface, policy versions (risk policy, trust policy, check registry));
- decide an open decision: OD-1 model, OD-3 gold set and labels, OD-5 check thresholds;
- go beyond the Issue's scope, or proceed when its acceptance criteria are unclear or contradict the SDD, POLICY or ARCHITECTURE;
- change a UX flow or screen in a way that differs from the prototype or SDD;
- do anything security-related: secrets, API-key handling, CI secrets, repository settings, rulesets, or `.github/` permissions (never change rulesets);
- add a dependency that makes network calls, or any external service;
- run a destructive operation: force-push, deleting branches, `reset --hard` on shared branches, deleting data or audit files, or closing other people's Issues/PRs;
- use real data, or send the LLM anything beyond H4.

Secrets and test data: POLICY D-2/D-3 (env vars only, synthetic CSVs only).

**How to ask:**
1. Leave Status as it is.
2. Add the label `needs-owner`, creating it if missing.
3. Comment on the Issue with the exact question.
4. Stop.

## 9. Changing a hard rule

Write `docs/adr/NNNN-short-title.md` with **Context**, **Decision**, **Consequences** and the rule it replaces. Open it as its own PR into `dev`. The owner approves it before any code depends on it, and this file is updated in the same PR.

## 10. Project agents, skills and rules

To be added in later steps. List each one here with a one-line purpose.

- Agents (`.claude/agents/`):
  - `guardrail-reviewer`: read-only review of a diff against hard rules, contracts, scope and DoD. Use before Agent review, after fixes, and before no-self-merge merges. You pass four scratchpad files: the diff, the Issue, the PR description draft and the test-evidence-runner report.
  - `test-evidence-runner`: runs only the §4 test/build commands and returns unedited results. Use before opening a PR, after fixes, and before merge.
- Skills: `.claude/skills/` (none yet)
- Rules: `.claude/rules/` (none yet)
