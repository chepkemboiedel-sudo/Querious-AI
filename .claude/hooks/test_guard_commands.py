"""Self-test for guard_commands.py (stdlib unittest only).

Run from the repo root: py -3.12 -B -m unittest discover -s .claude/hooks -v
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard_commands as g  # noqa: E402

RUNNER = "test-evidence-runner"


def shell(command, agent_type=None, tool="Bash", agent_id=None):
    payload = {"tool_name": tool, "tool_input": {"command": command}, "cwd": "C:/repo"}
    if agent_type:
        payload["agent_type"] = agent_type
        payload["agent_id"] = agent_id or "a1"
    elif agent_id:
        payload["agent_id"] = agent_id
    return g.decide(payload)


def file_tool(tool, **tool_input):
    return g.decide({"tool_name": tool, "tool_input": tool_input})


class PartA_Allow(unittest.TestCase):
    CASES = [
        "git status",
        "git push -u origin chore/guardrails",
        "git push origin dev",
        "git commit -m 'chore: add guard'",
        "git branch -d merged-branch",
        "git reset --soft HEAD~1",
        "git clean -n",
        "gh pr create --base dev --title x --body-file b.md",
        "gh pr create -B dev --title x",
        "gh pr create --base=dev",
        "gh pr edit 5 --title x",
        "gh pr edit 5 --base dev",
        "gh pr merge 46 --merge",
        "cat .env.example",
        "Get-Content .env.example",
        "cat docs/POLICY.md",
        "echo hello",
    ]

    def test_allow(self):
        for cmd in self.CASES:
            for tool in ("Bash", "PowerShell"):
                with self.subTest(cmd=cmd, tool=tool):
                    self.assertIsNone(shell(cmd, tool=tool)[0])

    def test_file_tools_allow(self):
        self.assertIsNone(file_tool("Read", file_path="C:/repo/.env.example")[0])
        self.assertIsNone(file_tool("Read", file_path="C:/repo/docs/POLICY.md")[0])
        self.assertIsNone(file_tool("Grep", pattern="KEY", path="C:/repo/docs")[0])
        self.assertIsNone(file_tool("Grep", pattern="KEY", glob="*.py")[0])
        self.assertIsNone(file_tool("Glob", pattern="**/*.py")[0])
        self.assertIsNone(file_tool("Glob", pattern=".env.example")[0])

    def test_other_tools_ignored(self):
        self.assertIsNone(g.decide({"tool_name": "Write", "tool_input": {"file_path": ".env"}})[0])


class PartA_Deny(unittest.TestCase):
    FORCE_PUSH = [
        "git push --force",
        "git push -f origin feature/x",
        "git push origin feature/x -f",
        "git push -uf origin feature/x",
        "git push --force-with-lease",
        "git push --force-with-lease=feature/x origin feature/x",
        "git push origin +feature/x",
        "git push origin '+HEAD:refs/heads/feature/x'",
        "git -C repo push --force",
        "cd backend && git push --force",
        "GIT_TRACE=1 git push -f",
    ]
    PR_BASE = [
        "gh pr create",
        "gh pr create --title x --body y",
        "gh pr create --base main",
        "gh pr create --base staging",
        "gh pr create -B main",
        "gh pr create -Bstaging",
        "gh pr create --base=main",
        "gh pr create --base feature/other",
        "gh pr create --base dev --base main",
        "gh pr edit 5 --base main",
        "gh pr edit 5 --base staging",
        "gh pr edit 5 -B main",
        "gh pr edit 5 --base=staging",
    ]
    ENV_SHELL = [
        "cat .env",
        "cat ./.env",
        "cat backend/.env.local",
        "type .env",
        "head -n 5 .env",
        "tail .env.production",
        "less .env",
        "more .env",
        "Get-Content .env",
        "Get-Content -Path '.env.local'",
        "gc .env",
        "cat .env*",
        "grep KEY .env",
        "wc -l < .env",
        "echo x && cat .env",
    ]

    def assert_deny(self, cmd, tool="Bash"):
        decision, reason, _ = shell(cmd, tool=tool)
        self.assertEqual(decision, g.DENY, f"{cmd!r} -> {decision} ({reason})")
        self.assertTrue(reason)

    def test_force_push(self):
        for cmd in self.FORCE_PUSH:
            with self.subTest(cmd=cmd):
                self.assert_deny(cmd)
                self.assert_deny(cmd, tool="PowerShell")

    def test_pr_base(self):
        for cmd in self.PR_BASE:
            with self.subTest(cmd=cmd):
                self.assert_deny(cmd)
                self.assert_deny(cmd, tool="PowerShell")

    def test_env_shell(self):
        for cmd in self.ENV_SHELL:
            with self.subTest(cmd=cmd):
                self.assert_deny(cmd)

    def test_env_file_tools(self):
        cases = [
            ("Read", {"file_path": "C:/repo/.env"}),
            ("Read", {"file_path": "C:\\repo\\backend\\.env.local"}),
            ("Grep", {"pattern": "KEY", "path": "C:/repo/.env"}),
            ("Grep", {"pattern": "KEY", "path": "C:/repo", "glob": ".env*"}),
            ("Grep", {"pattern": "KEY", "glob": "**/.env.production"}),
            ("Glob", {"pattern": "**/.env"}),
            ("Glob", {"pattern": ".env.*"}),
            ("Glob", {"pattern": "**/.env*", "path": "C:/repo"}),
        ]
        for tool, ti in cases:
            with self.subTest(tool=tool, ti=ti):
                self.assertEqual(file_tool(tool, **ti)[0], g.DENY)

    def test_two_blocked_segments_still_deny(self):
        self.assertEqual(shell("git reset --hard && git push --force")[0], g.DENY)


class PartA_DestructiveOwnerOnly(unittest.TestCase):
    """Row 7: deny (not ask), and tell the owner to run it themselves with '!'."""

    CASES = [
        "git reset --hard",
        "git reset --hard origin/dev",
        "git branch -D feature/x",
        "git branch -df feature/x",
        "git branch --delete --force feature/x",
        "git push --delete origin feature/x",
        "git push origin --delete feature/x",
        "git push -d origin feature/x",
        "git push origin :feature/x",
        "git clean -f",
        "git clean -fd",
        "git clean -xdf",
        "git clean --force",
    ]

    def test_deny_with_owner_instruction(self):
        for cmd in self.CASES:
            for tool in ("Bash", "PowerShell"):
                with self.subTest(cmd=cmd, tool=tool):
                    decision, reason, _ = shell(cmd, tool=tool)
                    self.assertEqual(decision, g.DENY, f"{cmd!r} -> {decision}")
                    self.assertIn("run it yourself with: ! git ", reason)

    def test_no_ask_decisions_remain(self):
        for cmd in self.CASES + PartA_Deny.FORCE_PUSH + PartA_Deny.PR_BASE:
            with self.subTest(cmd=cmd):
                self.assertNotEqual(shell(cmd)[0], g.ASK)


class PartB_Runner(unittest.TestCase):
    ALLOWED = [
        ".venv/Scripts/python.exe -m pytest",
        "./.venv/Scripts/python.exe -m pytest -q",
        "cd backend && .venv/Scripts/python.exe -m pytest -q",
        "cd backend && .venv/Scripts/python.exe -m pytest -v -x tests/test_health.py",
        ".venv/Scripts/python.exe -m pytest -k 'health and not slow' tests/test_health.py::test_ok",
        "pytest",
        "pytest -vv tests/test_api.py::test_load[small]",
        "cd frontend && npm test",
        "cd frontend && npm run build",
        "npm test",
        "git status",
        "git diff --stat",
        "git diff dev...HEAD",
        "git log --oneline -3",
        "py -3.12 --version",
        "node --version",
        "npm --version",
    ]
    VIOLATIONS = [
        "py --version",
        "py -3.12 --version --verbose",
        "python --version",
        "node --version && npm --version",
        "npm --version; echo x",
        "cd backend && .venv/Scripts/python.exe -m pytest -q; echo \"exit=$?\"",
        "cd \"/c/Users/Edel AIDEV/code/Querious-AI/backend\" && .venv/Scripts/python.exe -m pytest -q",
        "pip install -r requirements.txt",
        "npm ci",
        "npm run dev",
        "uvicorn app.main:app --reload",
        "py -3.12 -m venv .venv",
        "python -m pytest",
        ".venv/Scripts/python.exe -m pytest --cache-clear",
        ".venv/Scripts/python.exe -m pytest -p no:cacheprovider",
        ".venv/Scripts/python.exe -m pip install x",
        "npm test -- -u",
        "cd docs && pytest",
        "cd backend && pytest && rm -rf x",
        "cd backend; pytest",
        "pytest | tee out.txt",
        "pytest > out.txt",
        "pytest\nrm -rf x",
        "echo $ANTHROPIC_API_KEY",
        "pytest `whoami`",
        "git diff --output=patch.txt",
        "git commit -m x",
        "git checkout dev",
        "gh pr list",
        "rm -rf node_modules",
    ]

    def test_allowed_commands_logged_not_blocked(self):
        for cmd in self.ALLOWED:
            with self.subTest(cmd=cmd):
                decision, _, log = shell(cmd, agent_type=RUNNER)
                self.assertIsNone(decision)
                self.assertEqual(log["verdict"], "allowed", log)

    def test_log_mode_records_but_does_not_block(self):
        with mock.patch.object(g, "RUNNER_MODE", "log"):
            for cmd in self.VIOLATIONS:
                with self.subTest(cmd=cmd):
                    decision, _, log = shell(cmd, agent_type=RUNNER)
                    self.assertIsNone(decision)
                    self.assertEqual(log["verdict"], "would-block", log)
                    self.assertTrue(log["reason"])

    def test_enforce_mode_denies(self):
        with mock.patch.object(g, "RUNNER_MODE", "enforce"):
            for cmd in self.VIOLATIONS:
                with self.subTest(cmd=cmd):
                    self.assertEqual(shell(cmd, agent_type=RUNNER)[0], g.DENY)
            for cmd in self.ALLOWED:
                with self.subTest(cmd=cmd):
                    self.assertIsNone(shell(cmd, agent_type=RUNNER)[0])

    def test_part_a_still_enforced_for_runner_in_log_mode(self):
        with mock.patch.object(g, "RUNNER_MODE", "log"):
            decision, _, log = shell("git push --force", agent_type=RUNNER)
            self.assertEqual(decision, g.DENY)
            self.assertEqual(log["verdict"], g.DENY)
            self.assertEqual(shell("cat .env", agent_type=RUNNER)[0], g.DENY)
            self.assertEqual(shell("git reset --hard", agent_type=RUNNER)[0], g.DENY)

    def test_allowlist_only_applies_to_runner(self):
        with mock.patch.object(g, "RUNNER_MODE", "enforce"):
            for agent in (None, "Explore", "guardrail-reviewer"):
                with self.subTest(agent=agent):
                    decision, _, log = shell("pip install -r requirements.txt", agent_type=agent)
                    self.assertIsNone(decision)
                    self.assertIsNone(log)

    def test_subagent_without_agent_type_is_logged_as_diagnostic(self):
        decision, _, log = shell("npm ci", agent_id="a9")
        self.assertIsNone(decision)
        self.assertEqual(log["verdict"], "diagnostic")


class EndToEnd(unittest.TestCase):
    SCRIPT = Path(g.__file__)

    def run_hook(self, stdin_text):
        return subprocess.run([sys.executable, "-B", str(self.SCRIPT)], input=stdin_text,
                              capture_output=True, text=True, timeout=30)

    def test_deny_output_shape(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push --force"}}
        proc = self.run_hook(json.dumps(payload))
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"])

    def test_allow_prints_nothing(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        proc = self.run_hook(json.dumps(payload))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_bad_input_exits_zero_without_decision(self):
        proc = self.run_hook("not json")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_main_writes_runner_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "guard.log"
            payload = {"tool_name": "Bash", "agent_type": RUNNER, "agent_id": "a1",
                       "tool_input": {"command": "npm ci"}}
            buf = io.StringIO()
            with mock.patch.object(g, "LOG_PATH", log_path), \
                    mock.patch.object(g, "RUNNER_MODE", "log"), \
                    mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                    redirect_stdout(buf):
                self.assertEqual(g.main(), 0)
            self.assertEqual(buf.getvalue(), "")
            entry = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(entry["verdict"], "would-block")
            self.assertEqual(entry["agent_type"], RUNNER)


if __name__ == "__main__":
    unittest.main()
