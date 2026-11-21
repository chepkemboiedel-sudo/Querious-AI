"""Dataset loader: makes a CSV upload or the sample the one active dataset (US-01, RC-01).

The loader is the only code that writes the dataset's DuckDB file, and it writes it once,
at load time (ARCHITECTURE.md Section 4). It builds a new file in the staging folder,
closes it, then swaps it in place of the old one. A load that fails leaves the previous
active dataset untouched. After a load, only ``executor.connect_read_only`` opens the file.

What an upload must be (POLICY D-6): one ``.csv`` file, UTF-8 text, with a header row
and at least one data row, at most 50 MB (``MAX_UPLOAD_BYTES``). Anything else is
rejected with a ``DatasetError`` whose message says why. Nothing fails silently: either
the load completes and the dataset is active, or an error is raised.

The header check is deterministic (owner decision 1A on Issue #4). The first row is the
header, and it is rejected when a name is empty, two names are the same (DuckDB names are
case-insensitive), or a name is a number (a sign that the first row is data). The message
names the column and suggests a rename. Known limits, accepted by the owner: a header-less
file whose first row is all text cannot be told apart from a header by any rule, so it is
accepted; a real header with a numeric name such as ``2024`` is rejected (rename it ``y2024``).

ASSUMPTION-01: column names are expected to be in English. This is documented, not
enforced: any non-empty, unique header name is accepted.

Out of scope here (TMP-04): column types, example values, the schema profile and the
dataset fingerprint. The summary below holds table and column names only.
"""

from __future__ import annotations

import codecs
import csv
import io
import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import duckdb

from app.pipeline.storage import active_db_path, active_meta_path, data_dir, staging_dir

MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
HEADER_SAMPLE_BYTES = 64 * 1024
DELIMITERS = ",;\t|"

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"
SAMPLE_NAME = "Sample dataset (customers and orders)"
SAMPLE_TABLES = ("customers", "orders")

# The write connection may read the staged CSV, but never installs or loads extensions.
LOAD_CONFIG: dict[str, object] = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
}

_load_lock = threading.Lock()
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


class DatasetError(ValueError):
    """A file was rejected or could not be loaded. ``str(error)`` is the user message."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class TableSummary:
    name: str
    columns: list[str]


@dataclass(frozen=True)
class DatasetSummary:
    name: str
    kind: str  # "upload" or "sample"
    loaded_at: str
    tables: list[TableSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DatasetSummary":
        return cls(
            name=data["name"],
            kind=data["kind"],
            loaded_at=data["loaded_at"],
            tables=[TableSummary(t["name"], list(t["columns"])) for t in data["tables"]],
        )


# --- public API -----------------------------------------------------------------------

def load_csv_upload(source: BinaryIO, filename: str) -> DatasetSummary:
    """Validate an uploaded CSV and make it the active dataset (replacing any other)."""
    if not filename or not filename.lower().endswith(".csv"):
        raise DatasetError(
            "Only .csv files can be uploaded. Choose a CSV file with a header row.",
            reason="not_csv",
        )
    with _load_lock:
        staging = _fresh_staging_dir()
        try:
            csv_path = staging / "upload.csv"
            _copy_limited(source, csv_path)
            delimiter = _check_header(csv_path)
            table = table_name_for(filename)
            tables = _build_database(staging / "dataset.duckdb", [(table, csv_path, delimiter)])
            summary = DatasetSummary(Path(filename).name, "upload", _now(), tables)
            _activate(staging / "dataset.duckdb", summary)
            return summary
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def load_sample() -> DatasetSummary:
    """Make the bundled sample (customers and orders) the active dataset."""
    with _load_lock:
        staging = _fresh_staging_dir()
        try:
            sources = []
            for table in SAMPLE_TABLES:
                path = SAMPLE_DIR / f"{table}.csv"
                sources.append((table, path, _check_header(path)))
            tables = _build_database(staging / "dataset.duckdb", sources)
            summary = DatasetSummary(SAMPLE_NAME, "sample", _now(), tables)
            _activate(staging / "dataset.duckdb", summary)
            return summary
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def active_dataset() -> DatasetSummary | None:
    """The active dataset's summary, read from disk, so it survives a restart."""
    meta, db = active_meta_path(), active_db_path()
    if not (meta.is_file() and db.is_file()):
        return None
    return DatasetSummary.from_dict(json.loads(meta.read_text(encoding="utf-8")))


def table_name_for(filename: str) -> str:
    """A safe table name from the file name: ``Sales 2025.csv`` -> ``sales_2025``."""
    stem = Path(filename).stem.lower()
    name = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    if not name:
        return "dataset"
    return f"t_{name}" if name[0].isdigit() else name


# --- steps ----------------------------------------------------------------------------

def _fresh_staging_dir() -> Path:
    path = staging_dir() / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def _copy_limited(source: BinaryIO, target: Path) -> None:
    """Copy the upload, stopping as soon as it passes the size limit; check it is text."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    size = 0
    with target.open("wb") as out:
        while chunk := source.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise DatasetError(
                    f"The file is larger than {MAX_UPLOAD_MB} MB. Upload a CSV of {MAX_UPLOAD_MB} MB or less.",
                    reason="too_large",
                )
            _check_text(decoder, chunk)
            out.write(chunk)
    _check_text(decoder, b"", final=True)
    if size == 0:
        raise DatasetError("The file is empty. Upload a CSV with a header row and data.", reason="empty")


def _check_text(decoder: codecs.IncrementalDecoder, chunk: bytes, final: bool = False) -> None:
    try:
        decoder.decode(chunk, final=final)
    except UnicodeDecodeError:
        raise DatasetError(
            "The file is not a UTF-8 text CSV. Save it as CSV (UTF-8) and upload it again.",
            reason="not_csv",
        ) from None
    if b"\x00" in chunk:
        raise DatasetError(
            "The file is not a text CSV. Save it as CSV (UTF-8) and upload it again.",
            reason="not_csv",
        )


def _check_header(path: Path) -> str:
    """Return the delimiter, or raise if the first row is not a usable header."""
    with path.open("rb") as raw:
        head = raw.read(HEADER_SAMPLE_BYTES).decode("utf-8", errors="ignore").lstrip("﻿")
    first_line = head.splitlines()[0] if head.strip() else ""
    if not first_line.strip():
        raise DatasetError(
            "The first row is empty. The CSV needs a header row with a name for each column.",
            reason="no_header",
        )
    delimiter = _guess_delimiter(first_line)
    header = next(csv.reader(io.StringIO(head), delimiter=delimiter))
    names = [cell.strip() for cell in header]
    for position, n in enumerate(names, start=1):
        if not n:
            raise DatasetError(
                f"Column {position} in the header row has no name. Give it a name, "
                f"for example 'column_{position}', or add a header row if the file has none.",
                reason="no_header",
            )
        if _NUMBER.fullmatch(n):
            raise DatasetError(
                f"The column name '{n}' is a number, so the first row looks like data, not a header. "
                f"Rename it, for example '{n}' → 'y{n.lstrip('+-')}', or add a header row if the file has none.",
                reason="no_header",
            )
    seen: set[str] = set()
    for n in names:
        if n.lower() in seen:
            raise DatasetError(
                f"The header row uses the column name '{n}' more than once. "
                "Column names must be unique: rename one of them.",
                reason="no_header",
            )
        seen.add(n.lower())
    return delimiter


def _guess_delimiter(first_line: str) -> str:
    counts = {d: first_line.count(d) for d in DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _build_database(db_path: Path, sources: list[tuple[str, Path, str]]) -> list[TableSummary]:
    """Write every table into a new DuckDB file, then close it. The only write, ever."""
    tables: list[TableSummary] = []
    con = duckdb.connect(str(db_path), config=dict(LOAD_CONFIG))
    try:
        for table, csv_path, delimiter in sources:
            try:
                con.execute(
                    f'CREATE TABLE "{table}" AS SELECT * FROM read_csv(?, header = true, '
                    "delim = ?, strict_mode = true, encoding = 'utf-8')",
                    [str(csv_path), delimiter],
                ).fetchall()
            except duckdb.Error as exc:
                raise DatasetError(
                    "The file could not be read as a CSV: some rows don't match the header "
                    "(for example, a different number of columns). Fix the file and upload it again.",
                    reason="unreadable",
                ) from exc
            rows = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if rows == 0:
                raise DatasetError(
                    "The file has a header row but no data rows. Upload a CSV with data.",
                    reason="no_rows",
                )
            columns = [r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position", [table]).fetchall()]
            tables.append(TableSummary(table, columns))
        con.execute("CHECKPOINT").fetchall()
    finally:
        con.close()
    return tables


def _activate(new_db: Path, summary: DatasetSummary) -> None:
    """Swap the new file in for the old one, so only one dataset is ever active."""
    data_dir().mkdir(parents=True, exist_ok=True)
    meta_tmp = new_db.with_suffix(".json")
    meta_tmp.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    try:
        os.replace(new_db, active_db_path())
    except PermissionError as exc:  # Windows: the old file is still open somewhere
        raise DatasetError(
            "The current dataset is in use, so it could not be replaced. Try again.",
            reason="busy",
        ) from exc
    os.replace(meta_tmp, active_meta_path())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
