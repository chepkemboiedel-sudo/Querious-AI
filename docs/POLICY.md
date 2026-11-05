# Querious AI — Policy

> **Read this before working on any Issue that changes what users see, what data goes where, or how work is approved.** It holds the product, privacy and process rules that don't depend on code structure.
> The technical structure is in [ARCHITECTURE.md](ARCHITECTURE.md). Direction is in [ROADMAP.md](ROADMAP.md). Tasks and status are in the [GitHub Project](https://github.com/users/chepkemboiedel-sudo/projects/4).
>
> Owner: Edel Kiprop · Last reviewed: November 2026 · Changes need the owner's approval in a pull request.

## 1. Roles and permissions

### Product roles (SDD 1.2, Figure 2)

| Role | Can | Cannot |
|---|---|---|
| Business user (primary) | Load a CSV or the sample, ask, clarify, read answers and evidence, reopen history, rate answers. | Write SQL, edit data, edit business terms. |
| Data steward | Define terms, metrics and allowed joins in `semantic_layer.yaml` (offline). | Use a steward screen (there is none in the MVP). |
| Decision-maker | Act on answers that can be traced through the audit record. | (Doesn't use the app directly.) |
| Developer / evaluator | Run tests, the gold-set evaluation (US-13) and the optional baseline (US-14). | Expose the baseline to business users. |

### Engineering roles (repo and Project)

| Who | May | Must not |
|---|---|---|
| Human owner (Edel) | Approve scope, mark Issues **Reviewed**, move Issues to **Ready**, approve ADRs, merge `dev → staging → main`, label the gold set. | Commit from the AiDev account. |
| AiDev agent (Claude Code) | Draft Issues (always **Human Review = Pending**), work Ready Issues on `feature/*` branches, open and merge PRs into `dev` when tests pass. | Mark Issues Reviewed, move to Ready, push to `staging` or `main`, change rulesets or secrets, decide an open decision (Section 7). |

## 2. Terminology

Use these words in code, UI text and Issues, with these meanings.

| Term | Meaning |
|---|---|
| **Question** | One plain-English request. Each question gets one audit record. |
| **Interpretation** | The meaning used to answer. When there were alternatives, it is the one the user chose. It is shown with the answer. |
| **Query plan (IR)** | The validated JSON plan. Not SQL. |
| **Attempt** | One planning try. At most 3 per question. |
| **Answer released** | Every mandatory check passed and a result is shown. Anything else is **not executed** or **executed but failed checks**. |
| **Honest failure** | No answer and no score, with the reason, what was tried and a rephrasing. |
| **Verification support** | High / Medium / Low from the RC-17 policy, always with its reasons. **Never** call it "confidence", "accuracy" or a percentage. |
| **Risk class** | Low / Medium / High from RC-18. Decides which checks are mandatory. |
| **Rows considered** | Input rows after joins and filters, before grouping or top-N (RC-19). Not the number of result rows. |
| **Provenance** | Sources, dataset fingerprint, columns, filters, date boundaries and rows considered. |
| **Business term** | A steward definition, for example *active customer* = a customer with an order in the last 90 days. |
| **Gold set** | The frozen, human-labeled questions with known answers used by US-13. |

## 3. Product rules

- **P-1 No number without a query.** Every value shown comes from an executed result (RC-03). If in doubt, fail honestly.
- **P-2 Ask, don't guess.** Ambiguous questions offer 2–3 meanings. Nothing is preselected, Continue stays disabled until the user picks one, and "None of these, rephrase" runs nothing (US-04, DD-06).
- **P-3 Show the evidence.** Every released answer shows its interpretation, terms, risk class, checks, verification support with reasons, and provenance. SQL and the raw plan appear only inside "How I got this" (RC-13).
- **P-4 Say what is supported before running.** Show operations and risk before execution. Reject forecasting, causal "why" questions, data changes and missing data early, with a reason (RC-20, US-07).
- **P-5 Business definitions win.** Terms mean what `semantic_layer.yaml` says, not what the model assumes (RC-05).
- **P-6 Follow-ups are new questions.** At most 3, built from templates. Each one goes through the full pipeline (RC-21).
- **P-7 Feedback and history are kept.** Ratings are stored with the audit record. Reopening an answer never reruns it (US-08, US-09).

## 4. Privacy and data handling

- **D-1 Data stays on the machine.** Only schema metadata, business terms, the question and error messages may go to the LLM provider (RC-07). Example values are **off** (OQ-05). Turning them on is the owner's decision.
- **D-2 Secrets.** The API key is set only as an environment variable. Never commit or paste keys, tokens or `.env` files into code, Issues, PRs, logs or videos.
- **D-3 Test data.** Use the fictional sample dataset and small synthetic CSVs. Never put real personal or company data in the repo, Issues or the gold set.
- **D-4 History is kept until the user deletes it.** Audit records stay in a local SQLite file, with no telemetry. There is no "clear history" button in the MVP. Deleting the file clears history. A clear button would be new scope and needs an SDD change.
- **D-5 Read-only.** Querious never changes the user's data (RC-01). Requests to change data are refused.
- **D-6 What a dataset is (US-01, ASSUMPTION-01).**
  - One CSV with a header row, up to 50 MB, with English column names. Anything else is rejected with a clear message.
  - **One active dataset at a time.** It is kept locally so it is still there after a restart.
  - "Change dataset" replaces it. Old answers in history still show the fingerprint of the dataset they used.

## 5. Responsible-use rules

- **E-1 No over-claiming (RISK-04).** Passing checks shows the steps worked, not that the meaning or the data is right. UI text never says an answer is "correct" or "guaranteed".
- **E-2 Accessibility (RC-14).** Keyboard navigation, contrast, screen-reader labels, status never shown by color alone, and every chart paired with its table.
- **E-3 Third-party AI.** Use of the LLM provider follows its terms. The model in use is recorded in each audit record (RC-09).
- **E-4 Honest evaluation.** Report measured results with their denominators. The 80% accuracy figure is a target, not a result (US-13). Never tune on the gold answers.

## 6. Work process

1. AI-drafted Issues start as **Status = Backlog** and **Human Review = Pending**, with the `ai-generated` label.
2. The owner reviews each one: scope matches the plan, SDD IDs are right, acceptance criteria are testable, design references and images are there, blockers are correct, and verification is defined. Then the owner sets **Reviewed**.
3. Only Reviewed Issues whose blockers are done move to **Ready**. Agents take Ready Issues only.
4. One Issue per PR into `dev`, with `Closes #n` and the SDD IDs. Then **Agent Review → Done in Dev**. Promotions go to `staging` and `main` and are approved by the owner.
5. If an Issue conflicts with the SDD, this file or ARCHITECTURE.md, **stop**: comment on the Issue and move it back to Ready.

## 7. Open decisions (owner only)

| ID | Decision | Status |
|---|---|---|
| OD-1 / OQ-01 | LLM model | Open: compare candidates on the gold set |
| OD-2 / OQ-02 | IR coverage | **Decided:** SDD 2.3 list only |
| OD-3 / OQ-03 | Gold set and dataset | Open: the owner labels 40–50 questions |
| OD-4 / OQ-05 | Example values to the LLM | **Decided:** off |
| OD-5 / RISK-02 | Initial check thresholds | Open: approve in TMP-18 and TMP-23 |
| OD-6 | Stage transport | **Decided:** polling (ARCHITECTURE.md Section 8) |

**Interview record (November 2026).** Claude drafted this file and ARCHITECTURE.md, then asked the owner about the open points. Decisions:

- the dataset is kept after a restart,
- one dataset at a time,
- history is kept until the file is deleted (no clear button in the MVP),
- stage progress uses polling.

OD-1, OD-3 and OD-5 stay open on purpose. Agents must not decide them.
