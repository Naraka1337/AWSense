"""FastAPI application entrypoint, startup schema seeding, and router mounting."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.overview import router as overview_router
from app.api.recommendations import router as recommendations_router
from app.api.resources import router as resources_router
from app.api.simulate import router as simulate_router
from app.api.traffic import router as traffic_router
from app.core import database
from app.services.repository import seed_database
from app.services.telemetry_provider import get_telemetry_provider


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize database tables and idempotently seed telemetry data on startup."""
    database.create_tables(database.engine)
    with database.SessionLocal() as session:
        seed_database(session, provider=get_telemetry_provider())
    yield


app = FastAPI(
    title="AWSense API",
    description="Backend API for AWSense Cloud Management Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for the frontend (set CORS_ORIGINS comma-separated in production).
_cors_env = os.getenv("CORS_ORIGINS", "*").strip()
_cors_origins = (
    ["*"]
    if not _cors_env or _cors_env == "*"
    else [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview_router)
app.include_router(resources_router)
app.include_router(alerts_router)
app.include_router(traffic_router)
app.include_router(recommendations_router)
app.include_router(simulate_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "Welcome to AWSense API"}


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
