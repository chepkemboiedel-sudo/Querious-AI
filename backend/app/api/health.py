"""Liveness endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the backend process is up. Touches no data and no model."""
    return {"status": "ok"}
