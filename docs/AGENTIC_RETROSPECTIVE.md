# Agentic workflow retrospective: first run (Issue #3)

Date: 2026-11-18. Scope: the config PRs that set up the workflow (#46 agents and docs, #47 hooks and the `issue-to-pr` skill) and its first Issue run (#3 → PR #48). Sources: Issue #3 and its timeline, PRs #46–#48, Project 4 status events, `.claude/**`, `.claude/hooks/guard.log`, the local Stage 4 session transcript (`1c8917db…`), AiDev memory notes and the owner's run notes.

## Issue and outcome

#3 (scaffold, CI, H12–H14 import scan) shipped in PR #48: 2 commits, 40 backend tests plus a frontend smoke test, and CI green on the first push (3 jobs, now required on `dev`). The owner checked all 8 ACs by hand, approved, and told AiDev to merge. Elapsed time from start to merge: 29 min (20:01–20:30 UTC).

## What worked without human correction

- The `issue-to-pr` skill loaded first. Eligibility was checked from Project fields, and Status moved Ready → In progress → Agent review → Done in Dev, each move by AiDev at the right step.
- Branch from `dev`, `type:` commits, and a PR body that followed the §6 template.
- Two review rounds, then a stop. In round 1 the reviewer found two real scan gaps (folder skipping; `-e`/URL requirements). Both were fixed, with tests.
- The `.github/` question (action pinning) was escalated to #3 with `needs-owner` and options (a)–(c). AiDev did not decide it, and did not self-merge.
- The lead kept the runner report unedited. It added a separate "Lead note" for the capital-I mismatch, which it had checked byte by byte.
- When `gh issue view --comments` printed nothing, the lead switched to `--json` and wrote that down.
- The auto-mode classifier blocked `pip install httpx2`, an unvetted package ("Undermining Oversight"). The lead then kept `httpx`.

## Problems, evidence and likely root cause

| # | Observation | Evidence | Likely root cause |
| --- | --- | --- | --- |
| 1 | The review stop rule depends on a severity scale the reviewer doesn't use. #46 took 6 rounds. In #3 the rule only worked through a memory note. | Skill §4: "Blocker, High and Medium… stop once no finding is Medium or higher". The reviewer's output only has `blocker/major/minor`. The mapping exists only in machine-local memory (`review-stop-criterion.md`). | The skill and the agent were written separately. The lesson from #46 went into memory, not into versioned config. A fresh session found "Medium" undefined (3.6). |
| 2 | The skill's read command for the Issue prints nothing on this machine, so the reviewer's `issue.md` could silently be empty. | Transcript: the `gh issue view 3 --comments` output was blank, and the lead switched to `--json`. Skill §1.1 and §4.2 still use the plain command. Memory: `gh-issue-view-quirk.md`. | Environment quirk. The fix lives only in memory. |
| 3 | A hook `ask` did not prompt, and `git reset --hard` ran (#47 testing). The Stage 4 run used auto mode, not the planned accept-edits mode. | `guard_commands.py:12-13`. All 15 local transcripts record `permissionMode: auto`, and #3 started in auto at 20:01Z. | Sessions on this machine start in auto mode. The guard design assumed a prompting mode. This was already fixed by changing those commands to deny. |
| 4 | The runner allowlist is log-only and doesn't match the runner's prompt. | `guard.log` 12:09:14 and 12:12:18 show `would-block` for `py -3.12 backend/scripts/import_scan.py`. The hook allows `npm --version` and read-only git. `test-evidence-runner.md` lists neither, and its output says "you don't run git". | One allowlist is written in two places. The scan command arrived in #3 after the hook was written. |
| 5 | The runner changed its output: "Import scan" instead of `import scan`, in both rounds. | PR #48 body, line 47 vs `import_scan.py:293`. The lead's note is in the same PR body. | The model restates output instead of quoting it. Nothing captures the output mechanically. |
| 6 | AiDev posted the owner's decision (c) under its own account, and the owner had to re-post it. | #3 comments at 20:19:16 (`edelkiprop970-sys`, "Owner decision (in session)") and 20:28:22 (owner). | §8 "How to ask" covers asking, but not how to record the owner's answer. `gh` on this machine is logged in as AiDev. |
| 7 | AiDev's move to Done in Dev set off two Project workflows. They closed #3 and moved it to **Released**, a status §5 reserves for the owner. The lead's report said `Closes #3` had closed the Issue, which was wrong. | Transcript: the only calls after the merge are `gh pr merge 48 --merge --match-head-commit d3f26fa` (no `--delete-branch`) and `gh project item-edit` → Done in Dev. There is no `gh issue close`. The #3 timeline shows Done in Dev at 20:31:01 (AiDev), then closed at 20:31:02 by AiDev with `closer: ProjectV2 #4`, then Released at 20:31:05 (`github-project-automation`). The PR's base was `dev`, not the default branch, so `Closes #3` couldn't fire. | Project 4's built-in workflows **Auto-close issue** and **Item closed** (both enabled) conflict with CLAUDE.md §5's status ownership. The owner's correction set off the same chain again, which confirms that the trigger is Done in Dev. The lead read Status right after its own edit, before the workflows ran, so it reported the wrong cause and missed the jump. **Owner correction:** the owner reopened #3 at 21:16:18 and set Done in Dev at 21:20:06. The Project closed #3 again at 21:20:07 (`closer: ProjectV2`) and set Released at 21:20:09. The owner set Done in Dev again at 21:20:17, and it held. Final state: closed (completed), Status = Done in Dev. |
| 8 | Some owner chores were needed after the merge. | Required checks didn't save on the first try. They are now set (3 contexts on the `dev` ruleset). The remote branch stayed after the merge: AiDev's `gh pr merge` had no `--delete-branch` (it said so), and the repo has `delete_branch_on_merge: false`. The branch has since been deleted. The SHA-pin follow-up from (c) has no Issue yet. | GitHub settings, outside the agent's scope. |

## Recommended change (single, highest leverage): protect status ownership

The root cause is row 7. Project 4's automations turned AiDev's routine move to Done in Dev into "closed + Released", which overrode the §5 rule that Staging Candidate and Released belong to the owner. Neither the agent nor the owner noticed it during the run. The change has two parts:

1. **Owner (Project 4 setting):** stop **Auto-close issue** from firing on Done in Dev.
2. **Repo (`issue-to-pr` §7.4):** after moving an Issue to Done in Dev, wait about 15 s, then re-read the Issue state and the Project Status. If the Issue is closed, or Status is not Done in Dev, report it through the §8 `needs-owner` comment and change nothing.

## Why this should improve the next run

The move to Done in Dev happens on every Issue that merges, and before this change each of those moves produced a wrong status that only the owner may set. Part 1 removes the known trigger. Part 2 catches any automation we don't know about yet, and fixes the gap that misled the lead on #3: it read Status right after its own edit and reported a wrong cause. The agent reports instead of repairing, so status ownership stays with the owner.

## Additional candidates (not applied)

1. **Severity scale in step 4 (#1, #2):** use the reviewer's `blocker/major/minor` levels in the stop rule, and build `issue.md` with the `--json` form, stopping if the file is empty. That would make the repo independent of machine-local memory.
2. **Runner allowlist (#4):** add the scan command to the hook and make `test-evidence-runner.md` match the hook. Then the owner decides whether to switch it to enforce.
3. **Default permission mode (#3):** no change for now. Auto mode helped (the httpx2 block), and destructive commands are already denied. Don't rely on `ask`.
4. **Owner-decision recording (#6):** one line in §8. AiDev records an owner decision only as "Relayed by AiDev from the owner in session", or asks the owner to post it.
5. **SHA pinning (#8):** open the follow-up `chore/*` Issue agreed in (c).
6. **Runner fidelity (#5):** watch it. Add mechanical output capture only if it causes a wrong verdict.

## Final change made

- **Owner, 2026-11-18:** changed Project 4's **Auto-close issue** so that Done in Dev no longer closes Issues. The API shows the workflow is still enabled, so the trigger was changed rather than the workflow turned off. **Item closed** is unchanged: it still sets Released when an Issue is closed.
- **Owner verification:**
  1. Reopened #3 (21:26:30 UTC). It stayed open. This only shows that a reopen doesn't trigger a close, because Status was already Done in Dev.
  2. **Real test:** moved #3 to Agent review (21:30:10), then back to Done in Dev (21:30:32), and waited 30 s. **Result:** #3 stayed open with Status = Done in Dev. The timeline shows no close and no Released after 21:30:32, and AiDev re-checked at 21:32:33 with the same result. Before the change, the same move closed #3 within 1 s (20:31:02, 21:20:07).
- **Repo:** `.claude/skills/issue-to-pr/SKILL.md` §7.4 adds a post-merge status check. AiDev notes the time it set Done in Dev and doesn't use `sleep`. It runs `git switch dev`, `git pull --ff-only` and `git log` first. Then it re-reads the Issue state and the Project Status, and re-reads once more if less than 15 s have passed. If the Issue is closed or Status is not Done in Dev, it reports via `needs-owner` and changes nothing. If the second re-read is still under 15 s, it reports the real times. The step notes that the owner fixed the cause and that the check stays as a safeguard. Old §7.4 is now §7.5.
- **Fresh-session check:** a new session that loaded only the skill answered four questions about §7.4 without running any commands: the post-merge steps, what to do and not do if the Issue is closed and Released, whether the check applies when the owner says to merge, and how to wait about 15 s. All four answers were correct.

## Minor observation

- During Stage 6, AiDev briefly created a stray file outside the repository and then deleted it. Scratch files belong only in the session scratchpad, and a stray file should be reported, not silently removed.
