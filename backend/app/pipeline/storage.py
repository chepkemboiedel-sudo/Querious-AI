"""Where the active dataset lives on disk (ARCHITECTURE.md Section 9).

Everything is local (H12): one DuckDB file for the one active dataset, plus a small JSON
file with its display name, schema profile, example values and fingerprint, both in the local ``data/`` folder,
which is in ``.gitignore``. Set ``QUERIOUS_DATA_DIR`` to use another folder (tests do).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_ENV = "QUERIOUS_DATA_DIR"

ACTIVE_DB_NAME = "active_dataset.duckdb"
ACTIVE_META_NAME = "active_dataset.json"
STAGING_DIR_NAME = "staging"


def data_dir() -> Path:
    """The local data folder. Read on every call, so a changed env var takes effect."""
    configured = os.environ.get(DATA_DIR_ENV)
    return Path(configured) if configured else REPO_ROOT / "data"


def active_db_path() -> Path:
    return data_dir() / ACTIVE_DB_NAME


def active_meta_path() -> Path:
    return data_dir() / ACTIVE_META_NAME


def staging_dir() -> Path:
    return data_dir() / STAGING_DIR_NAME
