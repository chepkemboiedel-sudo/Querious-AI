"""Schema profile, example values and the dataset fingerprint (TMP-04; US-02, RC-07, RC-09, OQ-05).

Everything here is computed once, by the loader, on its own write connection before the
dataset file is closed (ARCHITECTURE.md Section 8, "Profiling"). The result is stored next
to the dataset, so the Data overview, the planner and the audit record read the same stored
facts and never open the dataset again: after a load only the executor opens it.

Two separate outputs, on purpose (H4, AR-3, POLICY D-1, OD-4):

- ``TableProfile``: table and column names, inferred types and row counts. This is the
  only part the LLM may see, and only through ``llm_schema()``.
- ``ExampleValues``: at most ``MAX_EXAMPLES`` values per text column, for local display on
  the Data overview (screen 2) only. ``llm_schema()`` takes no example values and has no
  option to include them; enabling that would need an ADR.

The fingerprint is a SHA-256 over the loaded file bytes: the same file always gives the
same value, and any one-byte change gives a different one. It does not depend on the file
name or the load time. The sample's fingerprint covers both of its files, with their table
names, in a fixed order.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

MAX_EXAMPLES = 5
TEXT_TYPE = "VARCHAR"
FINGERPRINT_PREFIX = "sha256:"

# table name -> column name -> example values (text columns only)
ExampleValues = dict[str, dict[str, list[str]]]


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    type: str  # the DuckDB type inferred at load, e.g. VARCHAR, BIGINT, DOUBLE, DATE


@dataclass(frozen=True)
class TableProfile:
    name: str
    row_count: int
    columns: list[ColumnProfile]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TableProfile":
        return cls(
            name=data["name"],
            row_count=int(data["row_count"]),
            columns=[ColumnProfile(c["name"], c["type"]) for c in data["columns"]],
        )


# --- profiling (loader only, on its write connection) ---------------------------------

def profile_table(con: duckdb.DuckDBPyConnection, table: str) -> tuple[TableProfile, dict[str, list[str]]]:
    """Profile one table that the loader has just written, and collect its example values."""
    columns = [
        ColumnProfile(name, data_type)
        for name, data_type in con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
    ]
    row_count = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    examples = {
        column.name: _examples(con, table, column.name)
        for column in columns
        if column.type == TEXT_TYPE
    }
    return TableProfile(table, int(row_count), columns), examples


def _examples(con: duckdb.DuckDBPyConnection, table: str, column: str) -> list[str]:
    """Up to five distinct, non-empty values, sorted, so the same file gives the same list."""
    quoted = '"' + column.replace('"', '""') + '"'
    rows = con.execute(
        f'SELECT DISTINCT {quoted} FROM "{table}" '
        f"WHERE {quoted} IS NOT NULL AND trim({quoted}) <> '' ORDER BY 1 LIMIT {MAX_EXAMPLES}"
    ).fetchall()
    return [r[0] for r in rows]


# --- fingerprint ----------------------------------------------------------------------

def format_fingerprint(sha256_hex: str) -> str:
    """An upload's fingerprint, from the SHA-256 the loader computes while copying it."""
    return FINGERPRINT_PREFIX + sha256_hex


def fingerprint_files(sources: list[tuple[str, Path]]) -> str:
    """Fingerprint several files (the sample): each table name and length, then its bytes."""
    digest = hashlib.sha256()
    for table, path in sources:
        data = path.read_bytes()
        digest.update(f"{table}\0{len(data)}\0".encode("utf-8"))
        digest.update(data)
    return format_fingerprint(digest.hexdigest())


# --- the LLM-facing serializer (H4) ---------------------------------------------------

def llm_schema(tables: list[TableProfile]) -> dict:
    """Table and column names and types only: what a prompt may contain (H4, AR-3, OD-4).

    No row values, no example values and no row counts. There is deliberately no
    parameter or setting that adds example values.
    """
    return {
        "tables": [
            {
                "name": table.name,
                "columns": [{"name": c.name, "type": c.type} for c in table.columns],
            }
            for table in tables
        ]
    }
