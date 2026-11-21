"""Load the active dataset's section of ``semantic_layer.yaml`` and check it against the schema.

``load_section`` is called each time a dataset becomes active (a load, or reading the
active dataset after a restart), so a steward's offline edit is always checked before it is
used. It reads the file again on every call. A definition that refers to a table or column
the dataset does not have, a term that uses an undeclared join, or a term or metric the
format cannot express is rejected with a ``SemanticLayerError`` whose message names the
definition and the problem (US-12, RC-05, H8).

This module knows nothing about how datasets are loaded: the caller passes the dataset's
key and its schema (table -> column -> type), so ``semantic`` never imports ``pipeline``.

The ``version`` of the result identifies exactly what was validated: the format version,
the dataset key and the section's content. It goes into the audit record (RC-09). The same
section always gives the same version; any change to it gives a different one.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.semantic.schema import (
    FORMAT_VERSION,
    DatasetSection,
    Filter,
    SemanticLayerFile,
    split_ref,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FILE_NAME = "semantic_layer.yaml"
PATH_ENV = "QUERIOUS_SEMANTIC_LAYER"
VERSION_PREFIX = "semantic-v1:sha256:"

# table name -> column name -> DuckDB type
Schema = dict[str, dict[str, str]]

DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS"}
NUMERIC_PREFIXES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT",
                    "UINTEGER", "UBIGINT", "UHUGEINT", "FLOAT", "DOUBLE", "DECIMAL", "REAL")
NUMERIC_AGGREGATIONS = {"sum", "avg"}


class SemanticLayerError(ValueError):
    """The file or the active dataset's section was rejected. ``str(error)`` names the problem."""


@dataclass(frozen=True)
class ActiveSemanticLayer:
    """The validated section of the active dataset. Empty when the dataset has no section."""

    dataset_key: str
    version: str
    section: DatasetSection


def semantic_layer_path() -> Path:
    """The file to read. Read on every call, so a changed env var takes effect (tests set it)."""
    configured = os.environ.get(PATH_ENV)
    return Path(configured) if configured else REPO_ROOT / FILE_NAME


def load_section(dataset_key: str, schema: Schema, path: Path | None = None) -> ActiveSemanticLayer:
    """Read the file, take ``dataset_key``'s section and validate it against ``schema``."""
    raw = _find_section(_read_file(path or semantic_layer_path()), dataset_key)
    section = _parse_section(dataset_key, raw)
    _check_against_schema(section, _case_insensitive(schema))
    return ActiveSemanticLayer(dataset_key, _version(dataset_key, raw is not None, section), section)


# --- reading --------------------------------------------------------------------------

def _read_file(path: Path) -> SemanticLayerFile:
    if not path.is_file():  # no file: no dataset has a section
        return SemanticLayerFile(format_version=FORMAT_VERSION)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        where = ""
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            where = f" at line {mark.line + 1}, column {mark.column + 1}"
        raise SemanticLayerError(f"{FILE_NAME} is not valid YAML{where}. Fix the file and load the dataset again.") from None
    if not isinstance(data, dict):
        raise SemanticLayerError(f"{FILE_NAME} must start with 'format_version: {FORMAT_VERSION}' and a 'datasets:' section.")
    try:
        return SemanticLayerFile.model_validate(data)
    except ValidationError as exc:
        raise SemanticLayerError(f"{FILE_NAME}: {_describe(exc)}") from None


def _find_section(file: SemanticLayerFile, dataset_key: str) -> dict | None:
    matches = [key for key in file.datasets if key.casefold() == dataset_key.casefold()]
    if len(matches) > 1:
        raise SemanticLayerError(
            f"{FILE_NAME} has more than one section for the dataset '{dataset_key}' "
            f"({', '.join(repr(m) for m in matches)}). Keep one of them."
        )
    if not matches:
        return None
    section = file.datasets[matches[0]]
    if section is not None and not isinstance(section, dict):
        raise SemanticLayerError(
            f"{FILE_NAME}, dataset '{matches[0]}': the section must be a mapping with "
            "'joins', 'terms' and 'metrics'."
        )
    return section or {}


def _parse_section(dataset_key: str, raw: dict | None) -> DatasetSection:
    if raw is None:
        return DatasetSection()
    try:
        return DatasetSection.model_validate(raw)
    except ValidationError as exc:
        raise SemanticLayerError(f"{FILE_NAME}, dataset '{dataset_key}': {_describe(exc, raw)}") from None


def _describe(exc: ValidationError, raw: dict | None = None) -> str:
    """The first problem, in plain words, with the name of the definition it is in."""
    errors = exc.errors()
    # An unsupported key says most about what is wrong, so it is reported first.
    error = next((e for e in errors if e["type"] == "extra_forbidden"), errors[0])
    loc = error["loc"]
    where = _where(loc, raw) or "the file"
    field = next((str(part) for part in reversed(loc) if isinstance(part, str)), "")
    if error["type"] == "extra_forbidden":
        if loc and loc[0] == "terms":
            return (
                f"{where} uses '{field}', which this format does not support. A term must be "
                "a declared join plus one filter with a distinct count (count_distinct, join, filter)."
            )
        return f"{where} uses '{field}', which this format does not support."
    if error["type"] == "missing":
        return f"{where} is missing '{field}'."
    message = error["msg"].removeprefix("Value error, ")
    return f"{where}: {message}."


def _where(loc: tuple, raw: dict | None) -> str:
    """``("terms", 0, "filter", "op")`` -> ``term 'active customer'`` (or ``term 1``)."""
    if len(loc) < 2 or loc[0] not in ("terms", "metrics", "joins") or not isinstance(loc[1], int):
        return "the section" if raw is not None else ""
    kind = loc[0][:-1]
    try:
        name = raw[loc[0]][loc[1]].get("name") if raw else None
    except (AttributeError, IndexError, KeyError, TypeError):
        name = None
    return f"{kind} '{name}'" if isinstance(name, str) and name.strip() else f"{kind} {loc[1] + 1}"


# --- checks against the dataset's schema ----------------------------------------------

def _case_insensitive(schema: Schema) -> dict[str, tuple[str, dict[str, tuple[str, str]]]]:
    """DuckDB names are case-insensitive: folded name -> (real name, folded column -> (name, type))."""
    return {
        table.casefold(): (table, {col.casefold(): (col, typ) for col, typ in columns.items()})
        for table, columns in schema.items()
    }


def _column_type(schema: dict, what: str, ref: str) -> str:
    table, column = split_ref(ref)
    if table.casefold() not in schema:
        raise SemanticLayerError(
            f"The {what} refers to the table '{table}', which does not exist in this dataset."
        )
    real_table, columns = schema[table.casefold()]
    if column.casefold() not in columns:
        raise SemanticLayerError(
            f"The {what} refers to the column '{ref}', which does not exist in the table '{real_table}'."
        )
    return columns[column.casefold()][1]


def _check_against_schema(section: DatasetSection, schema: dict) -> None:
    joins = {}
    for join in section.joins:
        what = f"join '{join.name}'"
        _column_type(schema, what, join.left)
        _column_type(schema, what, join.right)
        left_table, right_table = (split_ref(join.left)[0].casefold(), split_ref(join.right)[0].casefold())
        if left_table == right_table:
            raise SemanticLayerError(f"The {what} must connect two different tables.")
        joins[join.name.casefold()] = {left_table, right_table}

    for term in section.terms:
        what = f"term '{term.name}'"
        _column_type(schema, what, term.count_distinct)
        _check_filter(schema, what, term.filter)
        join_tables = joins.get(term.join.casefold())
        if join_tables is None:
            raise SemanticLayerError(
                f"The {what} uses the join '{term.join}', which is not declared for this dataset. "
                "Declare it under 'joins' or use a declared join."
            )
        used = {split_ref(term.count_distinct)[0].casefold(), split_ref(term.filter.column)[0].casefold()}
        if not used <= join_tables:
            raise SemanticLayerError(
                f"The {what} cannot be expressed with the join '{term.join}': its counted column and "
                "its filter column must be in the two tables that the join connects."
            )

    for metric in section.metrics:
        what = f"metric '{metric.name}'"
        column_type = _column_type(schema, what, metric.column)
        if metric.aggregation in NUMERIC_AGGREGATIONS and not column_type.upper().startswith(NUMERIC_PREFIXES):
            raise SemanticLayerError(
                f"The {what} uses '{metric.aggregation}' on the column '{metric.column}', "
                f"which is {column_type}, not a number."
            )


def _check_filter(schema: dict, what: str, condition: Filter) -> None:
    column_type = _column_type(schema, what, condition.column)
    if condition.op == "within_last_days" and column_type.upper() not in DATE_TYPES:
        raise SemanticLayerError(
            f"The {what} uses 'within_last_days' on the column '{condition.column}', "
            f"which is {column_type}, not a date."
        )


# --- version --------------------------------------------------------------------------

def _version(dataset_key: str, has_section: bool, section: DatasetSection) -> str:
    content = {
        "format_version": FORMAT_VERSION,
        "dataset": dataset_key.casefold(),
        "section": section.model_dump(mode="json") if has_section else None,
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return VERSION_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
