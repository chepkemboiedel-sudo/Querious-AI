"""The H12/H13/H14 import scan catches planted violations and passes on the real repository."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_scan.py"
_spec = importlib.util.spec_from_file_location("import_scan", SCRIPT)
import_scan = importlib.util.module_from_spec(_spec)
sys.modules["import_scan"] = import_scan  # dataclasses need the module registered
_spec.loader.exec_module(import_scan)


def plant(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rules(root: Path) -> list[str]:
    return sorted(v.rule for v in import_scan.scan(root))


def test_real_repository_is_clean() -> None:
    assert import_scan.scan(import_scan.REPO_ROOT) == []


# --- H13: model SDK outside backend/app/llm/ ------------------------------------------

@pytest.mark.parametrize(
    "rel, source",
    [
        ("backend/app/api/routes.py", "import anthropic\n"),
        ("backend/app/pipeline/planner.py", "from openai import OpenAI\n"),
        ("backend/app/pipeline/x.py", "from google import genai\n"),
        ("backend/app/pipeline/y.py", "import langchain_anthropic\n"),
        ("backend/app/audit/z.py", "import importlib\nimportlib.import_module('anthropic')\n"),
        ("eval/runner.py", "import anthropic.types\n"),
    ],
)
def test_h13_model_sdk_outside_llm_is_caught(tmp_path: Path, rel: str, source: str) -> None:
    plant(tmp_path, rel, source)
    assert rules(tmp_path) == ["H13"]


def test_h13_model_sdk_inside_llm_is_allowed(tmp_path: Path) -> None:
    plant(tmp_path, "backend/app/llm/anthropic_provider.py", "import anthropic\n")
    assert rules(tmp_path) == []


def test_h13_names_in_strings_and_comments_are_ignored(tmp_path: Path) -> None:
    plant(tmp_path, "backend/app/api/doc.py", '# import anthropic\nNOTE = "import openai"\n')
    assert rules(tmp_path) == []


def test_h13_model_sdk_in_frontend_is_caught(tmp_path: Path) -> None:
    plant(tmp_path, "frontend/package.json",
          json.dumps({"dependencies": {"react": "^19.0.0", "@anthropic-ai/sdk": "^1.0.0"}}))
    plant(tmp_path, "frontend/src/api.ts", "import OpenAI from 'openai';\n")
    assert rules(tmp_path) == ["H13", "H13"]


# --- H12: hosted-database drivers and account libraries --------------------------------

@pytest.mark.parametrize("source", ["import psycopg2\n", "from fastapi_users import FastAPIUsers\n",
                                    "import mysql.connector\n"])
def test_h12_python_import_is_caught(tmp_path: Path, source: str) -> None:
    plant(tmp_path, "backend/app/audit/store.py", source)
    assert rules(tmp_path) == ["H12"]


@pytest.mark.parametrize("line", ["psycopg2-binary==2.9.9", "Flask_Login>=0.6", "PyJWT  # tokens"])
def test_h12_requirements_entry_is_caught(tmp_path: Path, line: str) -> None:
    plant(tmp_path, "backend/requirements.txt", f"fastapi==1.0\n{line}\n")
    assert rules(tmp_path) == ["H12"]


@pytest.mark.parametrize("line", [
    "-e git+https://github.com/psycopg/psycopg2.git#egg=psycopg2",
    "https://example.invalid/pymongo-4.0.tar.gz#egg=pymongo",
    "psycopg2 @ https://example.invalid/psycopg2.tar.gz",
])
def test_h12_editable_and_url_requirements_are_caught(tmp_path: Path, line: str) -> None:
    plant(tmp_path, "backend/requirements.txt", f"-r base.txt\n{line}\n")
    assert rules(tmp_path) == ["H12"]


def test_unnamed_url_requirement_fails_closed(tmp_path: Path) -> None:
    plant(tmp_path, "backend/requirements-dev.txt", "-e git+https://example.invalid/pkg.git\n")
    assert rules(tmp_path) == ["SCAN"]


def test_h12_package_json_dependency_is_caught(tmp_path: Path) -> None:
    plant(tmp_path, "frontend/package.json",
          json.dumps({"dependencies": {"pg": "^8.0.0"}, "devDependencies": {"@auth0/auth0-react": "^2"}}))
    assert rules(tmp_path) == ["H12", "H12"]


def test_h12_frontend_import_is_caught(tmp_path: Path) -> None:
    plant(tmp_path, "frontend/src/db.ts", 'import { createClient } from "@supabase/supabase-js";\n')
    assert rules(tmp_path) == ["H12"]


# --- H14: backend/app must not import eval/ --------------------------------------------

@pytest.mark.parametrize("source", ["import eval\n", "from eval.runner import run\n", "import eval.baseline\n"])
def test_h14_app_importing_eval_is_caught(tmp_path: Path, source: str) -> None:
    plant(tmp_path, "backend/app/api/compare.py", source)
    assert rules(tmp_path) == ["H14"]


def test_h14_eval_may_import_pipeline(tmp_path: Path) -> None:
    plant(tmp_path, "eval/runner.py", "from app.pipeline import planner\n")
    assert rules(tmp_path) == []


# --- general behaviour -------------------------------------------------------------------

def test_unparsable_python_fails_closed(tmp_path: Path) -> None:
    plant(tmp_path, "backend/app/api/broken.py", "def (:\n")
    assert rules(tmp_path) == ["SCAN"]


@pytest.mark.parametrize("folder", ["build", "dist", ".hidden", "node_modules", "venv"])
def test_source_trees_are_scanned_in_any_folder(tmp_path: Path, folder: str) -> None:
    plant(tmp_path, f"backend/app/pipeline/{folder}/x.py", "import anthropic\n")
    plant(tmp_path, f"eval/{folder}/y.py", "import openai\n")
    assert rules(tmp_path) == ["H13", "H13"]


def test_dependency_and_hidden_dirs_are_skipped(tmp_path: Path) -> None:
    plant(tmp_path, "frontend/node_modules/x/index.js", "require('pg');\n")
    plant(tmp_path, "backend/.venv/lib/site.py", "import anthropic\n")
    assert rules(tmp_path) == []


def test_cli_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert import_scan.main(["--root", str(tmp_path)]) == 0
    plant(tmp_path, "backend/app/api/routes.py", "import anthropic\n")
    assert import_scan.main(["--root", str(tmp_path)]) == 1
    assert "[H13]" in capsys.readouterr().out
