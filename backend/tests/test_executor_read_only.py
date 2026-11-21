"""RC-01 / H3: every write through the executor's read-only connection fails (Issue #4)."""

from io import BytesIO
from pathlib import Path

import duckdb
import pytest

from app.pipeline import executor, loader

WRITES = [
    "INSERT INTO sales VALUES ('West', 1)",
    "UPDATE sales SET units = 0",
    "DELETE FROM sales",
    "DROP TABLE sales",
    "ALTER TABLE sales ADD COLUMN extra INTEGER",
    "CREATE TABLE extra (a INTEGER)",
    "CREATE VIEW v AS SELECT 1",
    "CREATE SCHEMA s",
    "CREATE MACRO m(a) AS a",
    "CREATE SEQUENCE seq",
    "TRUNCATE sales",
    "COPY sales TO '{dir}/out.csv'",
    "ATTACH '{dir}/other.duckdb' AS other",
    "INSTALL httpfs",
    "SET enable_external_access = true",
    "SET access_mode = 'read_write'",
    "SELECT * FROM read_csv('{dir}/../anything.csv')",
]


@pytest.fixture
def loaded(data_dir: Path) -> Path:
    loader.load_csv_upload(BytesIO(b"region,units\nNorth,12\nSouth,7\n"), "sales.csv")
    return data_dir / "active_dataset.duckdb"


@pytest.mark.parametrize("statement", WRITES)
def test_write_through_read_only_connection_fails(loaded: Path, data_dir: Path, statement: str) -> None:
    before = loaded.read_bytes()
    con = executor.connect_read_only()
    try:
        with pytest.raises(duckdb.Error):
            con.execute(statement.format(dir=data_dir.as_posix())).fetchall()
    finally:
        con.close()

    assert loaded.read_bytes() == before
    assert not (data_dir / "out.csv").exists()
    assert not (data_dir / "other.duckdb").exists()
    con = executor.connect_read_only()
    try:
        assert con.execute("SELECT count(*), sum(units) FROM sales").fetchone() == (2, 19)
    finally:
        con.close()


def test_temp_objects_stay_in_memory_and_never_reach_the_file(loaded: Path) -> None:
    before = loaded.read_bytes()
    con = executor.connect_read_only()
    try:
        con.execute("CREATE TEMP TABLE scratch AS SELECT 1 AS a").fetchall()
    finally:
        con.close()

    assert loaded.read_bytes() == before
    con = executor.connect_read_only()
    try:
        names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    finally:
        con.close()
    assert names == {"sales"}


def test_connection_is_opened_read_only(loaded: Path) -> None:
    con = executor.connect_read_only()
    try:
        settings = dict(con.execute(
            "SELECT name, value FROM duckdb_settings() WHERE name IN "
            "('access_mode', 'enable_external_access', 'lock_configuration', "
            "'autoinstall_known_extensions')"
        ).fetchall())
    finally:
        con.close()
    assert settings == {
        "access_mode": "read_only",
        "enable_external_access": "false",
        "lock_configuration": "true",
        "autoinstall_known_extensions": "false",
    }
