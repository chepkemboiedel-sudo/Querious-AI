"""Shared fixtures. Every test gets its own empty data folder, never the real data/."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.pipeline.storage import DATA_DIR_ENV

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "data"
    monkeypatch.setenv(DATA_DIR_ENV, str(folder))
    return folder


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def upload(client: TestClient, name: str, content: bytes):
    return client.post("/datasets/upload", files={"file": (name, content, "text/csv")})
