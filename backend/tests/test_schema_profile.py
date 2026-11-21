"""Issue #15 (TMP-04): schema profile, example values and dataset fingerprint.

US-02, RC-07, RC-09, OQ-05. Synthetic CSVs only (POLICY D-3).
"""

import hashlib
import importlib
import inspect
import json
from io import BytesIO
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from app.pipeline import executor, loader, schema_profile
from tests.conftest import FIXTURES, upload

# Row values that must never reach the LLM-facing schema. Distinctive on purpose, so a
# leak cannot hide behind a column name or a type.
PEOPLE_CSV = (
    "person,city,joined,score,active\n"
    "Zelda_Qx1,Northvale,2025-01-03,10,true\n"
    "Yusuf_Qx2,Eastport,2025-02-14,20,false\n"
    "Xena_Qx3,Northvale,2025-03-01,30,true\n"
    "Wanda_Qx4,Southmere,2025-04-22,40,false\n"
    "Victor_Qx5,Westbrook,2025-05-09,50,true\n"
    "Uma_Qx6,Eastport,2025-06-30,60,false\n"
    "Tariq_Qx7,Lakeside,2025-07-15,70,true\n"
).encode("utf-8")


def load_people(client: TestClient) -> dict:
    response = upload(client, "people.csv", PEOPLE_CSV)
    assert response.status_code == 200
    return response.json()["dataset"]


def every_cell(content: bytes) -> set[str]:
    lines = content.decode("utf-8").splitlines()[1:]
    return {cell for line in lines for cell in line.split(",")}


def string_leaves(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(string_leaves(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(string_leaves(v) for v in value)) if value else set()
    return set()


# --- AC1: profile and fingerprint are computed at load and stored ---------------------

def test_profile_and_fingerprint_are_stored_with_the_dataset(client: TestClient, data_dir: Path) -> None:
    load_people(client)

    stored = json.loads((data_dir / "active_dataset.json").read_text(encoding="utf-8"))
    assert stored["fingerprint"].startswith("sha256:")
    assert stored["tables"][0]["row_count"] == 7
    assert stored["tables"][0]["columns"][0] == {"name": "person", "type": "VARCHAR"}
    assert "city" in stored["examples"]["people"]


def test_reading_the_profile_never_opens_the_dataset(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = load_people(client)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the dataset was opened after load")

    monkeypatch.setattr(duckdb, "connect", refuse)
    monkeypatch.setattr(executor, "connect_read_only", refuse)

    assert client.get("/datasets/active").json()["dataset"] == expected


def test_summary_stored_before_profiling_counts_as_no_dataset(client: TestClient, data_dir: Path) -> None:
    load_people(client)
    meta = data_dir / "active_dataset.json"
    old = json.loads(meta.read_text(encoding="utf-8"))
    old = {"name": old["name"], "kind": old["kind"], "loaded_at": old["loaded_at"],
           "tables": [{"name": "people", "columns": ["person", "city"]}]}
    meta.write_text(json.dumps(old), encoding="utf-8")

    assert client.get("/datasets/active").json() == {"dataset": None}


# --- AC2: the endpoint returns names, inferred types and row counts --------------------

def test_endpoint_returns_names_inferred_types_and_row_count(client: TestClient) -> None:
    load_people(client)

    table = client.get("/datasets/active").json()["dataset"]["tables"][0]

    assert table["name"] == "people"
    assert table["row_count"] == 7
    assert table["columns"] == [
        {"name": "person", "type": "VARCHAR"},
        {"name": "city", "type": "VARCHAR"},
        {"name": "joined", "type": "DATE"},
        {"name": "score", "type": "BIGINT"},
        {"name": "active", "type": "BOOLEAN"},
    ]


def test_types_and_row_counts_for_a_fixture_and_the_sample(client: TestClient) -> None:
    sales = upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes()).json()["dataset"]
    assert sales["tables"][0]["row_count"] == 3
    assert {c["name"]: c["type"] for c in sales["tables"][0]["columns"]} == {
        "region": "VARCHAR", "product": "VARCHAR", "units": "BIGINT", "revenue": "DOUBLE",
    }

    sample = client.post("/datasets/sample").json()["dataset"]
    rows = {t["name"]: t["row_count"] for t in sample["tables"]}
    assert rows == {"customers": 20, "orders": 80}
    customers = {c["name"]: c["type"] for c in sample["tables"][0]["columns"]}
    assert customers["signup_date"] == "DATE"
    assert customers["customer_id"] == "BIGINT"


# --- AC3: at most five example values per text column, for the Data overview -----------

def test_at_most_five_examples_per_text_column_only(client: TestClient) -> None:
    examples = load_people(client)["examples"]["people"]

    assert set(examples) == {"person", "city"}  # text columns only
    assert examples["person"] == ["Tariq_Qx7", "Uma_Qx6", "Victor_Qx5", "Wanda_Qx4", "Xena_Qx3"]
    assert examples["city"] == ["Eastport", "Lakeside", "Northvale", "Southmere", "Westbrook"]


def test_examples_are_distinct_and_skip_empty_values() -> None:
    content = b"tag,n\nred,1\n,2\nred,3\n   ,4\nblue,5\n"
    summary = loader.load_csv_upload(BytesIO(content), "tags.csv")

    assert summary.examples["tags"]["tag"] == ["blue", "red"]


# --- AC4: the LLM-facing serializer has names and types only (H4, OD-4) --------------

def test_llm_schema_contains_no_row_or_example_values(client: TestClient) -> None:
    dataset = load_people(client)
    summary = loader.active_dataset()
    assert summary is not None

    payload = schema_profile.llm_schema(summary.tables)

    allowed = {t["name"] for t in dataset["tables"]}
    allowed |= {c["name"] for t in dataset["tables"] for c in t["columns"]}
    allowed |= {c["type"] for t in dataset["tables"] for c in t["columns"]}
    assert string_leaves(payload) <= allowed
    text = json.dumps(payload)
    for value in every_cell(PEOPLE_CSV) | string_leaves(dataset["examples"]):
        assert value not in text
    assert "7" not in text  # not even the row count


def test_llm_schema_has_only_name_and_type_fields(client: TestClient) -> None:
    client.post("/datasets/sample")
    summary = loader.active_dataset()
    assert summary is not None

    payload = schema_profile.llm_schema(summary.tables)

    assert set(payload) == {"tables"}
    for table in payload["tables"]:
        assert set(table) == {"name", "columns"}
        for column in table["columns"]:
            assert set(column) == {"name", "type"}
    sample_cells = every_cell((loader.SAMPLE_DIR / "customers.csv").read_bytes())
    sample_cells |= every_cell((loader.SAMPLE_DIR / "orders.csv").read_bytes())
    assert not (string_leaves(payload) & (sample_cells - {"customer_id"}))


def test_no_setting_can_add_example_values_to_the_llm_schema() -> None:
    # The serializer takes only the table profiles: no flag, option or examples argument.
    assert list(inspect.signature(schema_profile.llm_schema).parameters) == ["tables"]
    # Table profiles carry no example values, so there is nothing to switch on.
    assert {f for f in schema_profile.TableProfile.__dataclass_fields__} == {"name", "row_count", "columns"}
    assert {f for f in schema_profile.ColumnProfile.__dataclass_fields__} == {"name", "type"}


# --- AC5: the fingerprint is deterministic ---------------------------------------------

def test_same_file_gives_the_same_fingerprint() -> None:
    first = loader.load_csv_upload(BytesIO(PEOPLE_CSV), "people.csv").fingerprint
    again = loader.load_csv_upload(BytesIO(PEOPLE_CSV), "people.csv").fingerprint
    renamed = loader.load_csv_upload(BytesIO(PEOPLE_CSV), "renamed.csv").fingerprint

    assert first == again == renamed
    assert first == "sha256:" + hashlib.sha256(PEOPLE_CSV).hexdigest()


def test_one_byte_change_gives_a_different_fingerprint() -> None:
    changed = PEOPLE_CSV.replace(b"Zelda", b"Zeldb")
    assert len(changed) == len(PEOPLE_CSV)
    assert sum(a != b for a, b in zip(changed, PEOPLE_CSV)) == 1

    original = loader.load_csv_upload(BytesIO(PEOPLE_CSV), "people.csv").fingerprint
    different = loader.load_csv_upload(BytesIO(changed), "people.csv").fingerprint

    assert original != different


def test_sample_fingerprint_is_stable() -> None:
    assert loader.load_sample().fingerprint == loader.load_sample().fingerprint


# --- AC6: the profile and fingerprint survive a restart --------------------------------

def test_profile_and_fingerprint_are_available_after_restart(client: TestClient) -> None:
    before = load_people(client)
    client.close()

    # "Restart": reload the modules so no in-memory state survives, then a new client.
    import app.api.datasets
    import app.main

    importlib.reload(schema_profile)
    importlib.reload(loader)
    importlib.reload(app.api.datasets)
    importlib.reload(app.main)
    restarted = TestClient(app.main.app)

    after = restarted.get("/datasets/active").json()["dataset"]
    assert after == before
    assert after["fingerprint"] == "sha256:" + hashlib.sha256(PEOPLE_CSV).hexdigest()
