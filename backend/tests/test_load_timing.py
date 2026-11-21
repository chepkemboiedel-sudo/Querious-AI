"""US-01 timing: a 50 MB CSV is loaded and its table and columns available within 10 s.

Marked slow: run locally with ``pytest -m slow``, not in CI (Issue #4 Verification).
The CSV is generated in the test's temporary folder and never committed.
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.pipeline import executor, loader

LIMIT_SECONDS = 10.0


@pytest.mark.slow
def test_50_mb_csv_is_available_within_10_seconds(client: TestClient, tmp_path: Path) -> None:
    header = b"order_id,customer_id,order_date,category,status,amount\n"
    rows = []
    size = len(header)
    i = 0
    while True:
        row = f"{i},{i % 997},2025-{i % 12 + 1:02d}-{i % 28 + 1:02d},Home,completed,{i % 450}.{i % 100:02d}\n".encode()
        if size + len(row) > loader.MAX_UPLOAD_BYTES:
            break
        rows.append(row)
        size += len(row)
        i += 1
    path = tmp_path / "orders_50mb.csv"
    path.write_bytes(header + b"".join(rows))
    assert loader.MAX_UPLOAD_BYTES - 200 < path.stat().st_size <= loader.MAX_UPLOAD_BYTES

    start = time.perf_counter()
    with path.open("rb") as f:
        response = client.post("/datasets/upload", files={"file": ("orders_50mb.csv", f, "text/csv")})
    con = executor.connect_read_only()
    try:
        count = con.execute("SELECT count(*) FROM orders_50mb").fetchone()[0]
    finally:
        con.close()
    elapsed = time.perf_counter() - start

    print(f"\n50 MB load: {path.stat().st_size:,} bytes, {count:,} rows, {elapsed:.2f} s")
    assert response.status_code == 200
    assert response.json()["dataset"]["tables"][0]["columns"] == [
        "order_id", "customer_id", "order_date", "category", "status", "amount"
    ]
    assert count == len(rows)
    assert elapsed < LIMIT_SECONDS
