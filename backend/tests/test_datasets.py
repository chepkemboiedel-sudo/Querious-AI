"""Issue #4 (TMP-03): load a CSV or the sample into the one active, read-only dataset."""

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.pipeline import executor, loader
from tests.conftest import FIXTURES, upload


def column_names(table: dict) -> list[str]:
    return [c["name"] for c in table["columns"]]


def tables_in_active_file() -> set[str]:
    con = executor.connect_read_only()
    try:
        return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    finally:
        con.close()


# --- AC1: a valid CSV loads and its table and columns are available -------------------

def test_valid_csv_loads_with_table_and_columns(client: TestClient) -> None:
    response = upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes())

    assert response.status_code == 200
    dataset = response.json()["dataset"]
    assert dataset["kind"] == "upload"
    assert dataset["name"] == "valid_sales.csv"
    assert [t["name"] for t in dataset["tables"]] == ["valid_sales"]
    assert column_names(dataset["tables"][0]) == ["region", "product", "units", "revenue"]
    # load-time assertion: the table is in the DuckDB file and readable read-only
    con = executor.connect_read_only()
    try:
        assert con.execute("SELECT count(*) FROM valid_sales").fetchone()[0] == 3
    finally:
        con.close()


def test_semicolon_csv_and_utf8_bom_load() -> None:
    from io import BytesIO

    content = "﻿city;visits\nNorthvale;4\nEastport;9\n".encode("utf-8")
    summary = loader.load_csv_upload(BytesIO(content), "visits.csv")
    assert [c.name for c in summary.tables[0].columns] == ["city", "visits"]


def test_table_name_is_made_safe() -> None:
    assert loader.table_name_for("Sales 2025 (Q1).csv") == "sales_2025_q1"
    assert loader.table_name_for("2025.csv") == "t_2025"
    assert loader.table_name_for("---.csv") == "dataset"


# --- AC2: invalid files are rejected with a clear message ----------------------------

@pytest.mark.parametrize(
    ("name", "content", "status", "reason", "words"),
    [
        ("notes.txt", (FIXTURES / "notes.txt").read_bytes(), 415, "not_csv", "Only .csv files"),
        ("image.csv", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", 415, "not_csv", "not a"),
        ("latin1.csv", "name\nJos\xe9\n".encode("latin-1"), 415, "not_csv", "UTF-8"),
        ("headerless.csv", (FIXTURES / "headerless.csv").read_bytes(), 422, "no_header",
         "The column name '1' is a number"),
        ("dupes.csv", b"id,Name,name\n1,a,b\n", 422, "no_header", "'name' more than once"),
        ("blank_name.csv", b"id,,amount\n1,a,2\n", 422, "no_header",
         "Column 2 in the header row has no name. Give it a name, for example 'column_2'"),
        ("empty.csv", b"", 422, "empty", "empty"),
        ("header_only.csv", (FIXTURES / "header_only.csv").read_bytes(), 422, "no_rows", "no data rows"),
        ("ragged.csv", (FIXTURES / "ragged.csv").read_bytes(), 422, "unreadable", "don't match the header"),
    ],
)
def test_invalid_file_is_rejected_with_clear_message(
    client: TestClient, name: str, content: bytes, status: int, reason: str, words: str
) -> None:
    response = upload(client, name, content)

    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["reason"] == reason
    assert words in detail["message"]
    assert client.get("/datasets/active").json() == {"dataset": None}


def test_numeric_header_name_is_named_with_a_rename_suggestion(client: TestClient) -> None:
    # Owner decision 1A (Issue #4): a numeric name is rejected; the message names it and suggests a rename.
    response = upload(client, "by_year.csv", b"region,2024,2025\nNorth,10,12\n")

    assert response.status_code == 422
    message = response.json()["detail"]["message"]
    assert "The column name '2024' is a number" in message
    assert "Rename it, for example '2024' → 'y2024'" in message


def test_file_over_50_mb_is_rejected(client: TestClient) -> None:
    # Generated during the test, never committed (Issue #4 Verification).
    row = b"North,Widget,12,240.50\n"
    content = b"region,product,units,revenue\n" + row * (loader.MAX_UPLOAD_BYTES // len(row) + 1)
    assert len(content) > loader.MAX_UPLOAD_BYTES

    response = upload(client, "big.csv", content)

    assert response.status_code == 413
    assert response.json()["detail"]["message"].startswith("The file is larger than 50 MB")
    assert client.get("/datasets/active").json() == {"dataset": None}


def test_file_of_exactly_50_mb_is_not_rejected_for_size() -> None:
    from io import BytesIO

    header = b"region,units\n"
    row = b"North,12\n"
    body = row * ((loader.MAX_UPLOAD_BYTES - len(header)) // len(row))
    padding = b"N," + b"1" * (loader.MAX_UPLOAD_BYTES - len(header) - len(body) - 3) + b"\n"
    content = header + body + padding
    assert len(content) == loader.MAX_UPLOAD_BYTES

    summary = loader.load_csv_upload(BytesIO(content), "exact.csv")
    assert summary.tables[0].name == "exact"


def test_failed_load_keeps_the_previous_dataset(client: TestClient) -> None:
    upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes())

    rejected = upload(client, "headerless.csv", (FIXTURES / "headerless.csv").read_bytes())

    assert rejected.status_code == 422
    assert client.get("/datasets/active").json()["dataset"]["name"] == "valid_sales.csv"
    assert tables_in_active_file() == {"valid_sales"}


def test_staging_files_are_cleaned_up(client: TestClient, data_dir: Path) -> None:
    upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes())
    upload(client, "headerless.csv", (FIXTURES / "headerless.csv").read_bytes())

    assert list((data_dir / "staging").iterdir()) == []


# --- AC3: the bundled sample: customers and orders, one join -------------------------

def test_sample_loads_two_tables_with_one_join_key(client: TestClient) -> None:
    response = client.post("/datasets/sample")

    assert response.status_code == 200
    dataset = response.json()["dataset"]
    assert dataset["kind"] == "sample"
    assert [t["name"] for t in dataset["tables"]] == ["customers", "orders"]
    columns = {t["name"]: column_names(t) for t in dataset["tables"]}
    shared = set(columns["customers"]) & set(columns["orders"])
    assert shared == {"customer_id"}  # the one join: orders.customer_id -> customers.customer_id

    con = executor.connect_read_only()
    try:
        orphans = con.execute(
            "SELECT count(*) FROM orders o LEFT JOIN customers c USING (customer_id) "
            "WHERE c.customer_id IS NULL"
        ).fetchone()[0]
        unique_ids = con.execute(
            "SELECT count(*) = count(DISTINCT customer_id) FROM customers"
        ).fetchone()[0]
    finally:
        con.close()
    assert orphans == 0
    assert unique_ids is True


# --- AC4: the file is written once at load time; afterwards only read-only access ----

def test_loading_never_leaves_a_write_connection_open(client: TestClient) -> None:
    client.post("/datasets/sample")
    # A second, independent read-only open would fail on Windows/DuckDB if a writer held the file.
    first, second = executor.connect_read_only(), executor.connect_read_only()
    first.close()
    second.close()


def test_active_file_is_unchanged_by_reads(client: TestClient, data_dir: Path) -> None:
    client.post("/datasets/sample")
    before = (data_dir / "active_dataset.duckdb").read_bytes()

    con = executor.connect_read_only()
    try:
        con.execute("SELECT * FROM orders").fetchall()
    finally:
        con.close()

    assert (data_dir / "active_dataset.duckdb").read_bytes() == before


# --- AC5: the last loaded dataset survives a restart ---------------------------------

def test_last_dataset_is_available_after_restart(client: TestClient) -> None:
    upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes())
    client.close()

    # "Restart": reload the modules so no in-memory state survives, then a new client.
    import app.api.datasets
    import app.main

    importlib.reload(loader)
    importlib.reload(app.api.datasets)
    importlib.reload(app.main)
    restarted = TestClient(app.main.app)

    dataset = restarted.get("/datasets/active").json()["dataset"]
    assert dataset["name"] == "valid_sales.csv"
    assert column_names(dataset["tables"][0]) == ["region", "product", "units", "revenue"]
    con = executor.connect_read_only()
    try:
        assert con.execute("SELECT sum(units) FROM valid_sales").fetchone()[0] == 22
    finally:
        con.close()


def test_no_dataset_before_any_load(client: TestClient) -> None:
    assert client.get("/datasets/active").json() == {"dataset": None}
    with pytest.raises(executor.NoActiveDatasetError):
        executor.connect_read_only()


# --- AC6: change dataset replaces the active one; only one at a time -----------------

def test_change_dataset_replaces_the_active_one(client: TestClient, data_dir: Path) -> None:
    upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes())
    assert tables_in_active_file() == {"valid_sales"}

    client.post("/datasets/sample")
    assert tables_in_active_file() == {"customers", "orders"}

    upload(client, "other_products.csv", (FIXTURES / "other_products.csv").read_bytes())
    assert tables_in_active_file() == {"other_products"}
    assert client.get("/datasets/active").json()["dataset"]["name"] == "other_products.csv"
    assert sorted(p.name for p in data_dir.glob("*.duckdb")) == ["active_dataset.duckdb"]


# --- AC7: English column names are assumed, not enforced (ASSUMPTION-01) -------------

def test_non_english_column_names_are_accepted(client: TestClient) -> None:
    content = "région,menge\nNord,12\nSüd,7\n".encode("utf-8")

    response = upload(client, "verkauf.csv", content)

    assert response.status_code == 200
    assert column_names(response.json()["dataset"]["tables"][0]) == ["région", "menge"]
