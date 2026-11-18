---
name: issue-to-pr
description: Querious AI workflow for taking one Project 4 Issue from Ready to a PR into dev - eligibility check, Project status moves, branch from dev, test-evidence-runner and guardrail-reviewer rounds, the CLAUDE.md §6 PR evidence template, and the merge decision. Use when starting, continuing or finishing work on an Issue.
---

# Issue to PR

CLAUDE.md is the authority. This skill orders the steps and links to the rules; it doesn't restate them. If anything here seems to conflict with CLAUDE.md, CLAUDE.md wins: stop and ask (CLAUDE.md §8, "How to ask").

You never approve a PR, and you never merge one that needs owner approval (CLAUDE.md §5) until the owner has approved it on GitHub **and** tells you to merge.

## 1. Eligibility (CLAUDE.md §3)

1. Read the Issue: `gh issue view <n> --comments`. Owner comments refine the body.
2. Read its Project 4 fields: `gh project item-list 4 --owner chepkemboiedel-sudo --format json` and find the item for #n.
3. Continue only if Status = Ready, Human Review = Reviewed, and Executor = AI Dev or Pair, and every "Blocked by" Issue is done. Ignore "Human Review: Pending" footers in the body.
4. If any check fails, or `gh project` can't read the fields, report it and stop. Don't change any field.
5. For Pair Issues, list the decision points the Issue names. At each one, use CLAUDE.md §8 "How to ask".

## 2. Start

1. Read the sources that CLAUDE.md §2 triggers for this Issue.
2. Move Status Ready → **In progress** (CLAUDE.md §5).
3. Branch from an up-to-date `dev`: `git switch dev && git pull --ff-only && git switch -c <type>/<n>-<slug>`. The type is `feature`, `fix`, `docs` or `chore` (CLAUDE.md §5).

## 3. Build

- Scope is the acceptance criteria and non-goals only (CLAUDE.md §3).
- Follow the hard rules and their required tests (CLAUDE.md §1), and the decide-alone vs stop-and-ask list (CLAUDE.md §8).
- Commit messages: `type: short summary` (CLAUDE.md §5).

## 4. Evidence rounds

1. Run `test-evidence-runner` (CLAUDE.md §10) and keep its report unedited.
2. Write the four scratchpad files the reviewer expects (CLAUDE.md §10):
   - `diff.txt`: `git diff dev...HEAD`
   - `issue.md`: `gh issue view <n> --comments`
   - `pr-body-draft.md`: the template in section 6 below
   - `test-evidence.md`: the runner report
3. Run `guardrail-reviewer` with those paths.
4. Fix Blocker, High and Medium findings, or escalate them via CLAUDE.md §8. Then re-run the runner and the reviewer on the new diff.
5. **Stop rule:** stop re-running once no finding is Medium or higher. List each remaining Minor or Low finding in one line under "Accepted, not fixed" in the PR body. Don't keep iterating on wording.

## 5. Open the PR

1. `gh pr create --base dev --title "<type>: <summary>" --body-file <scratchpad>/pr-body-draft.md`. Always pass `--base dev`, because the guard hook denies anything else.
2. Move Status → **Agent review** (CLAUDE.md §5).

## 6. PR body template (CLAUDE.md §6)

```markdown
Closes #<n>

## What changed
## Acceptance criteria → evidence
| AC | Test or file |
## Test evidence
<test-evidence-runner summary, verdict ALL PASS; CI link once CI exists>
## Guardrail review
<verdict and its AC → evidence table>
### Review rounds
### Accepted, not fixed
## Hard rules touched and their tests
## SDD references
## Docs updated
```

## 7. Merge decision (CLAUDE.md §5)

1. Check the no-self-merge list in CLAUDE.md §5: the Issue number, and the changed paths (`git diff --name-only dev...HEAD`).
2. **If the PR is on the list, or the reviewer's final verdict isn't PASS:** stop. Report the PR link and wait. Merge only after the owner tells you to, and only if `gh pr view <n> --json reviews,mergeStateStatus` shows an APPROVED review from chepkemboiedel-sudo on the current head commit.
3. **Otherwise**, when the checks pass (CLAUDE.md §5): `gh pr merge <n> --merge`, then move Status → **Done in Dev**.
4. Never run `gh pr review --approve`. Never open, edit or merge PRs into `staging` or `main`. Never move anything to Ready or set Human Review.
