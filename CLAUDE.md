# Querious AI — Engineering Policy

This file is the policy every developer on Querious follows, human or AI. Claude Code reads it automatically at the start of each session in this repository.

Querious answers plain-English questions about a user's data and shows how each answer was found. Its core idea: **the AI suggests, the system checks.** The rules below protect that idea. They come from the Software Design Document (SDD), Sections 4 (RC rules) and 7.1 (DD decisions).

**Read these before starting any Issue:**

- `docs/ARCHITECTURE.md`: components, allowed relationships, contracts and architecture/security rules.
- `docs/POLICY.md`: roles, terminology, product, privacy and work-process rules, and the open decisions only the owner can make.
- `docs/ROADMAP.md`: phases and direction. The GitHub Project is the source of truth for tasks and status.
- `docs/plan/implementation-plan.md`: phase detail and the TMP-to-Issue inventory (`docs/backlog-map.md`).

---

## 1. Hard rules (do not break; changing one needs a human-approved ADR)

| ID | Rule | Source |
| --- | --- | --- |
| H1 | The LLM is used for exactly two jobs: checking whether a question is ambiguous, and drafting a query plan. It never executes queries, never produces the SQL that runs, and never writes user-facing explanations. | DD-01, RC-02 |
| H2 | The query plan is a JSON object validated by the Pydantic schema in the pipeline package. SQL is compiled from a validated plan by deterministic code (SQLGlot). Never execute SQL text that came from a model. | DD-02 |
| H3 | Data access is read-only. Each attempt runs one compiled `SELECT`, with a 15-second timeout and a 5,000-row limit. Deterministic helper `SELECT`s for checks and provenance (RC-23) are allowed only through the same safety gate and limits. No `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP` or `ALTER`, ever. | RC-01, RC-23 |
| H4 | Only schema metadata (table names, column names, types) and semantic-layer definitions are sent to the LLM. Row values, sample rows and query results are never sent. | RC-07 |
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

Each hard rule should have at least one automated test. Required tests:

- H3: compiled SQL is a single read-only `SELECT`; anything else is rejected before execution.
- H4: the payload sent to the LLM provider contains no row values.
- H5: a failed or empty pipeline run returns no numeric answer.
- H6: the correction loop stops after 3 attempts and logs each one.

---

## 2. How work flows through this repository

- **Branches:** `main` (released, human-controlled) ← `staging` (release candidate, human-controlled) ← `dev` (integration) ← `feature/*`, `fix/*`, `docs/*` (short-lived work branches).
- **AI developers** (the AiDev account) branch from `dev`, open pull requests into `dev`, and may merge their own pull request once tests pass.
- **Never** push to or open work directly against `staging` or `main`. Promotion is proposed with a `dev → staging` pull request and approved and merged by a human.
- **One Issue per pull request.** Start only from an Issue in the GitHub Project that is in **Ready** with **Human Review = Reviewed**. Never set Human Review yourself. Link it in the pull request description with `Closes #<number>` and move the card to **In Progress**, then **Agent Review**.
- **Commit messages:** `type: short summary`, where type is one of `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## 3. Definition of done

A pull request into `dev` is done when:

1. Every acceptance criterion in its Issue is met and checked off.
2. New behaviour has tests, and all tests pass locally and in CI.
3. No hard rule is broken, and any hard rule it touches has a test.
4. The pull request description lists the Issue, what changed, how it was tested, and the SDD references (US / RC IDs).

## 4. Secrets and data

- Never commit secrets: API keys, tokens, passwords, `.env` files. Use environment variables and keep `.env` in `.gitignore`.
- Never paste secrets or real user data into prompts, Issues or pull requests.
- Use small, synthetic sample CSVs in tests and `eval/`.

## 5. Stop and ask a human before you

- change or work around any hard rule (H1–H14);
- change the query-plan schema, the semantic-layer format or the audit-log format;
- add a dependency that makes network calls, or any new external service;
- touch CI secrets, repository settings, rulesets or anything under `.github/` that affects permissions;
- proceed when an Issue's acceptance criteria are unclear or contradict the SDD.

Ask by commenting on the Issue and moving its card back to **Ready**.

## 6. Soft decisions (free to change with normal review)

UI layout and styling, wording of messages, which checks are in the verification registry, library versions, folder structure inside a package, and the evaluation question set.

## 7. Changing a hard rule

Write an Architecture Decision Record in `docs/adr/NNNN-short-title.md` with **Context**, **Decision**, **Consequences** and the hard rule it replaces. Open it as its own pull request into `dev`. A human must approve it before any code depends on it, and this file is updated in the same pull request.

## 8. Planned layout

Created by the scaffolding Issue (TMP-01); see `docs/ARCHITECTURE.md` Section 11 and update both when it changes.

```text
backend/            FastAPI app
  app/api/          HTTP endpoints
  app/pipeline/     ambiguity check, planner, validator, compiler, executor, result checks, explainer
  app/llm/          LLM provider interface (the only place model SDKs are imported)
  app/audit/        SQLite audit log
  app/semantic/     semantic-layer loader and validator
  tests/
frontend/           React + TypeScript (Vite)
semantic_layer.yaml business terms, metrics, allowed joins
eval/               evaluation questions and runner (US-13, US-14)
docs/adr/           architecture decision records
```

## 9. Reference

- SDD: Sections 3 (user stories), 4 (RC rules), 5 (architecture), 7.1 (DD decisions).
- Interactive prototype: SDD Section 6.2 link.
