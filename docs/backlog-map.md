# TMP-to-Issue map

Final GitHub numbers for Implementation Plan items. The GitHub Project is the source of truth for status and order.

| TMP ID | Issue # | Title | Phase | Blocked by (#) |
|---|---|---|---|---|
| TMP-01 | #3 | Scaffold FastAPI backend, React frontend, pytest and CI | P1. Foundation and Data | None |
| TMP-02 | #14 | Implement LLM provider interface with server-side key handling | P1. Foundation and Data | #3 |
| TMP-03 | #4 | Load a CSV or the sample dataset into read-only DuckDB | P1. Foundation and Data | #3 |
| TMP-04 | #15 | Profile the schema and compute a dataset fingerprint | P1. Foundation and Data | #4 |
| TMP-05 | #16 | Load and validate semantic_layer.yaml per dataset | P1. Foundation and Data | #15 |
| TMP-06 | #17 | Create the SQLite audit store with append-only events | P1. Foundation and Data | #3 |
| TMP-07 | #18 | Build the Start and Data overview screens | P1. Foundation and Data | #4, #16 |
| TMP-08 | #8 | Define the query-plan IR schema in Pydantic | P2. Question pipeline | #3 |
| TMP-09 | #19 | Implement the LLM query planner | P2. Question pipeline | #14, #16, #8 |
| TMP-10 | #20 | Implement the plan validator and capability gate | P2. Question pipeline | #16, #8 |
| TMP-11 | #9 | Compile validated plans to one read-only SELECT with SQLGlot | P2. Question pipeline | #8, #20 |
| TMP-12 | #21 | Implement the safe executor with timeout and row limit | P2. Question pipeline | #4, #9 |
| TMP-13 | #22 | Build the templated plain-English summary | P2. Question pipeline | #21 |
| TMP-14 | #23 | Expose the question API with stage progress and audit events | P2. Question pipeline | #17, #19, #20, #9, #21, #22 |
| TMP-15a | #24 | Build the Ask and Working screens | P2. Question pipeline | #18, #23 |
| TMP-15b | #25 | Build the Answer screen with chart and table | P2. Question pipeline | #24 |
| TMP-16 | #26 | Implement the ambiguity check with schema-valid alternatives | P3. Clarify and Correctness | #16, #19, #23 |
| TMP-17 | #27 | Build the Clarify screen | P3. Clarify and Correctness | #24, #26 |
| TMP-18 | #28 | Implement base result sanity checks | P3. Clarify and Correctness | #21 |
| TMP-19 | #10 | Implement bounded self-correction with exact error feedback | P3. Clarify and Correctness | #20, #23, #28 |
| TMP-20 | #29 | Implement early rejection, honest failure and LLM service errors | P3. Clarify and Correctness | #20, #10 |
| TMP-21 | #30 | Build the Honest failure and service-unavailable screens | P3. Clarify and Correctness | #24, #29 |
| TMP-22 | #31 | Implement the deterministic risk classifier and check registry | P4. Trust and Verification | #20, #28 |
| TMP-23a | #32 | Implement Medium-risk checks | P4. Trust and Verification | #31 |
| TMP-23b | #33 | Implement High-risk join checks with helper SELECTs | P4. Trust and Verification | #32 |
| TMP-24 | #34 | Implement the deterministic trust policy with fixtures | P4. Trust and Verification | #10, #33 |
| TMP-25 | #35 | Implement the provenance builder | P4. Trust and Verification | #21, #33 |
| TMP-26 | #36 | Show the capability and risk preview before execution | P4. Trust and Verification | #24, #31 |
| TMP-27 | #6 | Build the Verification support and Data used cards | P4. Trust and Verification | #34, #35 |
| TMP-28 | #37 | Complete the RC-09 audit record | P5. Audit and History | #17, #34, #35 |
| TMP-29 | #38 | Build the correction replay from audit events | P5. Audit and History | #6, #37 |
| TMP-30 | #39 | Implement question history with reopen | P5. Audit and History | #25, #6, #37 |
| TMP-31 | #40 | Implement answer feedback | P5. Audit and History | #25, #37 |
| TMP-32 | #41 | Generate up to three schema-validated follow-up questions | P5. Audit and History | #20, #25 |
| TMP-33 | #42 | Build the frozen sample dataset and gold question set | P6. Evaluation and Hardening | #8 |
| TMP-34 | #7 | Implement the one-command evaluation harness and report | P6. Evaluation and Hardening | #42, #27, #30, #36, #38, #39, #40, #41 |
| TMP-35 | #43 | Run the accessibility and SDD acceptance pass | P6. Evaluation and Hardening | #27, #30, #36, #38, #39, #40, #41 |
| TMP-36 | #44 | Optional: build the isolated baseline comparison runner | P6. Evaluation and Hardening | #7 |

Lab 2 parent Issue #5 has no TMP item. It was closed as superseded by #8, #9 and #10.
