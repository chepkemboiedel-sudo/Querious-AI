"""Dependency and import scan for hard rules H12, H13 and H14 (CLAUDE.md section 1).

Fails (exit code 1) when the repository contains:

- H12: a hosted-database driver or a user-account/auth library, as a Python import,
  a ``requirements*.txt`` entry, a ``package.json`` dependency or a frontend import;
- H13: a model SDK imported anywhere outside ``backend/app/llm/`` (Python), or any
  model SDK in the frontend (the browser never calls a model, ARCHITECTURE.md 7);
- H14: any import of the top-level ``eval`` package from ``backend/app``.

Standard library only, so CI can run it before installing anything:

    py -3.12 backend/scripts/import_scan.py            # scans the repository root
    py -3.12 backend/scripts/import_scan.py --root DIR # scans another tree (tests)

Python files are parsed with ``ast``, so names inside strings and comments are ignored.
A Python file that cannot be parsed is reported as a failure (fail closed).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories never scanned: environments, dependencies, build output, VCS and tool config.
SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build", "venv", "site-packages"}

LLM_PACKAGE = PurePosixPath("backend/app/llm")
APP_PACKAGE = PurePosixPath("backend/app")

# --- H13: model SDKs --------------------------------------------------------------------
# Python module names. A dotted entry also matches its submodules.
PY_MODEL_SDKS = {
    "anthropic", "openai", "google.generativeai", "google.genai", "vertexai",
    "mistralai", "cohere", "ollama", "groq", "together", "litellm", "llama_index",
    "huggingface_hub",
}
PY_MODEL_SDK_PREFIXES = ("langchain",)  # langchain, langchain_core, langchain_openai, ...

NPM_MODEL_SDKS = {
    "@anthropic-ai/sdk", "openai", "@google/generative-ai", "@google/genai",
    "@mistralai/mistralai", "cohere-ai", "ollama", "groq-sdk", "ai", "langchain",
}
NPM_MODEL_SDK_SCOPES = ("@ai-sdk/", "@langchain/", "@anthropic-ai/")

# --- H12: hosted-database drivers and account/auth libraries ----------------------------
PY_HOSTED_DB_OR_ACCOUNTS = {
    # hosted / server database drivers and cloud data services
    "psycopg2", "psycopg", "asyncpg", "pymysql", "MySQLdb", "mysql.connector", "aiomysql",
    "pymongo", "motor", "redis", "cx_Oracle", "oracledb", "pyodbc", "pymssql", "snowflake",
    "google.cloud.bigquery", "google.cloud.firestore", "google.cloud.spanner",
    "firebase_admin", "supabase", "databricks", "boto3",
    # user accounts / authentication
    "fastapi_users", "flask_login", "authlib", "passlib", "jwt", "jose", "auth0",
    "django.contrib.auth",
}

# Distribution names as they appear in requirements files (compared after PEP 503 normalising).
PY_DIST_HOSTED_DB_OR_ACCOUNTS = {
    "psycopg2", "psycopg2-binary", "psycopg", "psycopg-binary", "asyncpg", "pymysql",
    "mysqlclient", "mysql-connector-python", "aiomysql", "pymongo", "motor", "redis",
    "cx-oracle", "oracledb", "pyodbc", "pymssql", "snowflake-connector-python",
    "snowflake-sqlalchemy", "google-cloud-bigquery", "google-cloud-firestore",
    "google-cloud-spanner", "firebase-admin", "supabase", "databricks-sql-connector", "boto3",
    "fastapi-users", "flask-login", "authlib", "passlib", "pyjwt", "python-jose",
    "auth0-python",
}

NPM_HOSTED_DB_OR_ACCOUNTS = {
    "pg", "postgres", "mysql", "mysql2", "mongodb", "mongoose", "redis", "ioredis",
    "oracledb", "mssql", "tedious", "@supabase/supabase-js", "firebase", "firebase-admin",
    "@planetscale/database", "@neondatabase/serverless", "@prisma/client", "prisma",
    "@aws-sdk/client-dynamodb", "passport", "next-auth", "@auth/core",
}
NPM_HOSTED_DB_OR_ACCOUNTS_SCOPES = ("@auth0/", "@clerk/", "@supabase/", "@firebase/")

PACKAGE_JSON_KEYS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
FRONTEND_SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']"""
)


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


# --- helpers ----------------------------------------------------------------------------

def _matches_module(name: str, banned: set[str], prefixes: tuple[str, ...] = ()) -> str | None:
    """Return the banned entry that ``name`` is, or is a submodule of, else None."""
    for entry in banned:
        if name == entry or name.startswith(entry + "."):
            return entry
    top = name.split(".", 1)[0]
    for prefix in prefixes:
        if top.startswith(prefix):
            return top
    return None


def _npm_package(spec: str) -> str:
    """'@scope/pkg/sub' -> '@scope/pkg'; 'pkg/sub' -> 'pkg'."""
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def _npm_match(package: str, banned: set[str], scopes: tuple[str, ...]) -> bool:
    return package in banned or any(package.startswith(s) for s in scopes)


def _normalise_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_under(rel: PurePosixPath, package: PurePosixPath) -> bool:
    return rel == package or package in rel.parents


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            yield path, PurePosixPath(path.relative_to(root).as_posix())


def _imported_modules(tree: ast.AST):
    """Yield (module name, line) for imports, from-imports and literal dynamic imports."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative imports stay inside their own package
                continue
            if node.module:
                yield node.module, node.lineno
                for alias in node.names:  # `from google import genai`
                    yield f"{node.module}.{alias.name}", node.lineno
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            arg = node.args[0]
            if name in {"import_module", "__import__"} and isinstance(arg, ast.Constant) \
                    and isinstance(arg.value, str):
                yield arg.value, node.lineno


# --- scanners ---------------------------------------------------------------------------

def _scan_python(path: Path, rel: PurePosixPath) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        return [Violation("SCAN", str(rel), getattr(exc, "lineno", 0) or 0,
                          f"could not parse file, so it was not checked: {exc}")]

    found: list[Violation] = []
    seen: set[tuple[str, int, str]] = set()
    in_llm = _is_under(rel, LLM_PACKAGE)
    in_app = _is_under(rel, APP_PACKAGE)

    def add(rule: str, line: int, message: str) -> None:
        if (rule, line, message) not in seen:
            seen.add((rule, line, message))
            found.append(Violation(rule, str(rel), line, message))

    for module, line in _imported_modules(tree):
        sdk = _matches_module(module, PY_MODEL_SDKS, PY_MODEL_SDK_PREFIXES)
        if sdk and not in_llm:
            add("H13", line, f"model SDK '{sdk}' imported outside backend/app/llm/")
        banned = _matches_module(module, PY_HOSTED_DB_OR_ACCOUNTS)
        if banned:
            add("H12", line, f"hosted-database or account library '{banned}' imported")
        if in_app and (module == "eval" or module.startswith("eval.")):
            add("H14", line, "backend/app imports the eval/ package")
    return found


def _scan_requirements(path: Path, rel: PurePosixPath) -> list[Violation]:
    found = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)
        if match and _normalise_dist(match.group(0)) in PY_DIST_HOSTED_DB_OR_ACCOUNTS:
            found.append(Violation("H12", str(rel), number,
                                   f"hosted-database or account dependency '{match.group(0)}'"))
    return found


def _scan_package_json(path: Path, rel: PurePosixPath) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [Violation("SCAN", str(rel), 0, f"could not parse file, so it was not checked: {exc}")]
    found = []
    for key in PACKAGE_JSON_KEYS:
        for package in sorted((data.get(key) or {})):
            if _npm_match(package, NPM_HOSTED_DB_OR_ACCOUNTS, NPM_HOSTED_DB_OR_ACCOUNTS_SCOPES):
                found.append(Violation("H12", str(rel), 0,
                                       f"hosted-database or account dependency '{package}' in {key}"))
            if _npm_match(package, NPM_MODEL_SDKS, NPM_MODEL_SDK_SCOPES):
                found.append(Violation("H13", str(rel), 0,
                                       f"model SDK '{package}' in {key}; the frontend never calls a model"))
    return found


def _scan_frontend_source(path: Path, rel: PurePosixPath) -> list[Violation]:
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for spec in JS_IMPORT_RE.findall(line):
            if spec.startswith((".", "/")):
                continue
            package = _npm_package(spec)
            if _npm_match(package, NPM_HOSTED_DB_OR_ACCOUNTS, NPM_HOSTED_DB_OR_ACCOUNTS_SCOPES):
                found.append(Violation("H12", str(rel), number,
                                       f"hosted-database or account library '{package}' imported"))
            if _npm_match(package, NPM_MODEL_SDKS, NPM_MODEL_SDK_SCOPES):
                found.append(Violation("H13", str(rel), number,
                                       f"model SDK '{package}' imported in the frontend"))
    return found


def scan(root: Path) -> list[Violation]:
    """Scan the tree under ``root`` and return every violation found."""
    violations: list[Violation] = []
    for path, rel in _iter_files(root):
        if path.suffix == ".py":
            violations += _scan_python(path, rel)
        elif re.fullmatch(r"requirements.*\.txt", path.name):
            violations += _scan_requirements(path, rel)
        elif path.name == "package.json":
            violations += _scan_package_json(path, rel)
        elif rel.parts[:1] == ("frontend",) and path.suffix in FRONTEND_SOURCE_SUFFIXES:
            violations += _scan_frontend_source(path, rel)
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to scan (default: repo root)")
    args = parser.parse_args(argv)

    violations = scan(args.root.resolve())
    for violation in violations:
        print(violation)
    if violations:
        print(f"import scan: FAILED with {len(violations)} violation(s)")
        return 1
    print("import scan: OK (H12, H13, H14)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
