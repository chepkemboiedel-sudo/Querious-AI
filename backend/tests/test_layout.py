"""The backend package layout matches docs/ARCHITECTURE.md Section 11."""

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package", ["api", "pipeline", "llm", "audit", "semantic"])
def test_app_package_exists(package: str) -> None:
    assert (BACKEND / "app" / package / "__init__.py").is_file()
