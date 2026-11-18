"""PreToolUse guard for Querious AI Claude Code sessions (stdlib only, run with ``py -3.12``).

Claude Code sends the hook input as JSON on stdin. This script prints a PreToolUse
decision as JSON on stdout (or nothing, to leave the normal permission flow alone)
and always exits 0.

Part A - every session (lead and subagents), always enforced:
  deny: force-push (--force, -f, --force-with-lease, +refspec);
        gh pr create without an explicit --base dev, or with any other base;
        gh pr edit --base staging|main;
        reading .env / .env.* (not .env.example) via Read, Grep, Glob or shell commands;
        git reset --hard, git branch -D, git push --delete, git clean -f (the message
        tells the owner to run it themselves with "!"; "ask" did not prompt in testing).

Part B - only when agent_type == "test-evidence-runner": a Bash allowlist of the
CLAUDE.md section 4 test/build commands, py -3.12/node/npm --version, and read-only
git status/diff/log.
RUNNER_MODE "log" records would-be blocks in guard.log and blocks nothing;
"enforce" denies them. Only the owner decides when to switch.

Self-test: py -3.12 -B -m unittest discover -s .claude/hooks -v
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shlex
import sys
from pathlib import Path

RUNNER_AGENT = "test-evidence-runner"
RUNNER_MODE = "log"  # "log" or "enforce". Switch only on the owner's instruction.
LOG_PATH = Path(__file__).resolve().parent / "guard.log"

DENY = "deny"
ASK = "ask"

SHELL_TOOLS = {"Bash", "PowerShell"}
FILE_TOOLS = {"Read", "Grep", "Glob"}
PUNCT = re.compile(r"[;&|()<>]+")
ENV_READERS = {
    "cat", "type", "head", "tail", "less", "more", "get-content", "gc",
    "grep", "rg", "sed", "awk", "source", "strings", "select-string", "sls",
}
PREFIX_WORDS = {"env", "command", "time", "nohup", "exec"}
GIT_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}

# Runner allowlist (CLAUDE.md section 4 test/build commands + read-only git).
VENV_PYTHON = {".venv/Scripts/python.exe", "./.venv/Scripts/python.exe"}
PYTEST_FLAGS = {"-q", "-v", "-vv", "-x"}
TEST_PATH = re.compile(r"[\w./-]+(::[\w\[\].,=-]+)*")
CD_TARGETS = {"backend", "frontend", "./backend", "./frontend"}
GIT_READ_ONLY = {"status", "diff", "log"}
VERSION_CHECKS = (["py", "-3.12", "--version"], ["node", "--version"], ["npm", "--version"])


# ---------------------------------------------------------------- parsing

def tokenize(command: str) -> list[str]:
    """Split a shell command into words and operator tokens (quotes removed)."""
    text = command.replace("\r", " ").replace("\n", " ; ")
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:  # unbalanced quotes: fall back to a quote-blind split
        words = re.findall(r"&&|\|\||[;|&()<>]|[^\s;|&()<>]+", text)
        return [w.strip("'\"") for w in words]


def segments(tokens: list[str]) -> tuple[list[list[str]], list[str]]:
    """Group tokens into simple commands; return them and the operators between them."""
    segs: list[list[str]] = []
    ops: list[str] = []
    cur: list[str] = []
    for tok in tokens:
        if PUNCT.fullmatch(tok):
            ops.append(tok)
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs, ops


def strip_prefix(seg: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrapper words such as env/command."""
    i = 0
    while i < len(seg) and (re.fullmatch(r"\w+=.*", seg[i]) or seg[i] in PREFIX_WORDS):
        i += 1
    return seg[i:]


def prog(token: str) -> str:
    name = re.split(r"[\\/]", token)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def basename(path: str) -> str:
    return re.split(r"[\\/]", path.strip().strip("'\""))[-1]


def is_env_name(path: str) -> bool:
    """True for .env, .env.<anything> and .env* globs; False for .env.example."""
    name = basename(path)
    if name == ".env.example":
        return False
    return name == ".env" or name.startswith(".env.") or name.startswith(".env*")


def short_has(arg: str, ch: str) -> bool:
    """True if arg is a short-option cluster (e.g. -uf) containing ch."""
    return re.fullmatch(r"-[A-Za-z0-9]+", arg) is not None and ch in arg[1:]


# ---------------------------------------------------------------- Part A

def check_git(seg: list[str]) -> tuple[str, str] | None:
    i = 1
    while i < len(seg):
        if seg[i] in GIT_OPTS_WITH_ARG:
            i += 2
        elif seg[i].startswith("-"):
            i += 1
        else:
            break
    if i >= len(seg):
        return None
    sub, args = seg[i], seg[i + 1:]
    positional = [a for a in args if not a.startswith("-")]

    if sub == "push":
        for a in args:
            if (a in ("--force", "--force-with-lease", "--force-if-includes")
                    or a.startswith("--force-with-lease=") or short_has(a, "f")):
                return DENY, f"Force-push is blocked ({a}). CLAUDE.md section 8: stop and ask the owner."
        for a in positional:
            if a.startswith("+"):
                return DENY, f"Force-push via +refspec is blocked ({a}). CLAUDE.md section 8: stop and ask the owner."
        for a in args:
            if a == "--delete" or short_has(a, "d") or (a.startswith(":") and len(a) > 1):
                return DENY, owner_only("git push --delete removes a remote branch", seg)
    elif sub == "reset" and "--hard" in args:
        return DENY, owner_only("git reset --hard discards uncommitted work", seg)
    elif sub == "branch":
        delete = "--delete" in args or short_has_any(args, "d") or short_has_any(args, "D")
        force = "--force" in args or short_has_any(args, "f") or short_has_any(args, "D")
        if delete and force:
            return DENY, owner_only("git branch -D force-deletes a branch", seg)
    elif sub == "clean":
        if "--force" in args or short_has_any(args, "f"):
            return DENY, owner_only("git clean -f deletes untracked files", seg)
    return None


def owner_only(what: str, seg: list[str]) -> str:
    """Block message for destructive commands the owner may run themselves."""
    return (f"{what}, so Claude may not run it (CLAUDE.md section 8). Owner: if you want it, "
            f"run it yourself with: ! {' '.join(seg)}")


def short_has_any(args: list[str], ch: str) -> bool:
    return any(short_has(a, ch) for a in args)


def pr_bases(args: list[str]) -> list[str]:
    bases = []
    for i, a in enumerate(args):
        if a in ("--base", "-B"):
            bases.append(args[i + 1] if i + 1 < len(args) else "")
        elif a.startswith("--base="):
            bases.append(a.split("=", 1)[1])
        elif a.startswith("-B") and len(a) > 2:
            bases.append(a[2:])
    return bases


def check_gh(seg: list[str]) -> tuple[str, str] | None:
    if len(seg) < 3 or seg[1] != "pr" or seg[2] not in ("create", "edit"):
        return None
    bases = pr_bases(seg[3:])
    if seg[2] == "create":
        if not bases:
            return DENY, ("gh pr create needs an explicit --base dev (the repo default is main). "
                          "CLAUDE.md section 5: PRs go into dev only.")
        if any(b != "dev" for b in bases):
            return DENY, f"PRs go into dev only (got --base {', '.join(bases)}). CLAUDE.md section 5."
    elif any(b in ("staging", "main") for b in bases):
        return DENY, "Changing a PR base to staging or main is owner-only. CLAUDE.md section 5."
    return None


def check_env_shell(seg: list[str]) -> tuple[str, str] | None:
    if prog(seg[0]) in ENV_READERS:
        for a in seg[1:]:
            if not a.startswith("-") and is_env_name(a):
                return DENY, f"Reading {a} is blocked (POLICY D-2: secrets stay out of the session)."
    return None


def check_shell(command: str) -> tuple[str, str] | None:
    tokens = tokenize(command)
    found: list[tuple[str, str]] = []
    for i, tok in enumerate(tokens):  # input redirection from an env file, e.g. "< .env"
        if PUNCT.fullmatch(tok) and "<" in tok and i + 1 < len(tokens) and is_env_name(tokens[i + 1]):
            found.append((DENY, f"Reading {tokens[i + 1]} is blocked (POLICY D-2)."))
    segs, _ = segments(tokens)
    for seg in segs:
        seg = strip_prefix(seg)
        if not seg:
            continue
        p = prog(seg[0])
        for check in (check_git if p == "git" else None,
                      check_gh if p == "gh" else None,
                      check_env_shell):
            if check:
                result = check(seg)
                if result:
                    found.append(result)
    for decision in (DENY, ASK):
        for d, reason in found:
            if d == decision:
                return d, reason
    return None


def check_file_tool(tool: str, tool_input: dict) -> tuple[str, str] | None:
    if tool == "Read":
        candidates = [tool_input.get("file_path")]
    elif tool == "Grep":
        candidates = [tool_input.get("path"), tool_input.get("glob")]
    else:  # Glob
        candidates = [tool_input.get("pattern"), tool_input.get("path")]
    for c in candidates:
        if isinstance(c, str) and c and is_env_name(c):
            return DENY, f"{tool} on {c} is blocked (POLICY D-2: secrets stay out of the session)."
    return None


# ---------------------------------------------------------------- Part B

def runner_violation(command: str) -> str | None:
    """Return why a runner command is outside the allowlist, or None if allowed."""
    if "$" in command or "`" in command:
        return "shell expansion ($ or backtick) is not allowed"
    segs, ops = segments(tokenize(command))
    if not segs:
        return "empty command"
    if ops:
        first = segs[0]
        if not (ops == ["&&"] and len(segs) == 2 and len(first) == 2
                and first[0] == "cd" and first[1].rstrip("/") in CD_TARGETS):
            return "only 'cd backend|frontend && <allowed command>' may be chained; no ;, |, redirects"
        segs = segs[1:]
    seg = segs[0]
    if seg in VERSION_CHECKS:
        return None
    if seg[0] in VENV_PYTHON and seg[1:3] == ["-m", "pytest"]:
        return pytest_violation(seg[3:])
    if seg[0] == "pytest":
        return pytest_violation(seg[1:])
    if seg in (["npm", "test"], ["npm", "run", "build"]):
        return None
    if seg[0] == "git" and len(seg) >= 2 and seg[1] in GIT_READ_ONLY:
        for a in seg[2:]:
            if a.startswith("--output"):
                return f"git {seg[1]} {a} writes a file"
        return None
    return f"not in the test-evidence-runner allowlist: {' '.join(seg)}"


def pytest_violation(args: list[str]) -> str | None:
    i = 0
    while i < len(args):
        a = args[i]
        if a in PYTEST_FLAGS:
            i += 1
        elif a == "-k" and i + 1 < len(args):
            i += 2
        elif not a.startswith("-") and TEST_PATH.fullmatch(a):
            i += 1
        else:
            return f"pytest argument not allowed: {a}"
    return None


# ---------------------------------------------------------------- entry points

def decide(payload: dict) -> tuple[str | None, str, dict | None]:
    """Return (decision or None, reason, log entry or None)."""
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    agent_type = payload.get("agent_type")
    agent_id = payload.get("agent_id")

    if tool in FILE_TOOLS:
        result = check_file_tool(tool, tool_input)
        return (result[0], result[1], None) if result else (None, "", None)
    if tool not in SHELL_TOOLS:
        return None, "", None

    command = tool_input.get("command") or ""
    result = check_shell(command)
    log = None
    if agent_type == RUNNER_AGENT:
        violation = runner_violation(command)
        log = {"agent_type": agent_type, "agent_id": agent_id, "tool": tool,
               "command": command, "cwd": payload.get("cwd"), "mode": RUNNER_MODE,
               "verdict": "would-block" if violation else "allowed", "reason": violation}
        if result:
            log["verdict"], log["reason"] = result[0], result[1]
        elif violation and RUNNER_MODE == "enforce":
            result = (DENY, f"test-evidence-runner allowlist: {violation}")
    elif agent_id and not agent_type:
        log = {"agent_type": None, "agent_id": agent_id, "tool": tool, "command": command,
               "cwd": payload.get("cwd"), "verdict": "diagnostic",
               "reason": "subagent call without agent_type"}
    if result:
        return result[0], result[1], log
    return None, "", log


def write_log(entry: dict) -> None:
    entry = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), **entry}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("guard_commands: could not parse hook input; no decision", file=sys.stderr)
        return 0
    try:
        decision, reason, log = decide(payload)
    except Exception as exc:  # fail closed for the runner only
        decision, reason, log = None, "", None
        if payload.get("agent_type") == RUNNER_AGENT and RUNNER_MODE == "enforce":
            decision, reason = DENY, f"guard error: {exc}"
        print(f"guard_commands: error {exc!r}", file=sys.stderr)
    if log:
        try:
            write_log(log)
        except OSError as exc:
            print(f"guard_commands: could not write log: {exc}", file=sys.stderr)
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
