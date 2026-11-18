"""FastAPI application entry point: `uvicorn app.main:app --reload` from backend/."""

from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(title="Querious AI")
app.include_router(health_router)
