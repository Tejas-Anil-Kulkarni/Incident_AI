"""IncidentMind AI FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.database import init_database
from config.logging import configure_logging

configure_logging()

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="IncidentMind AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)

# Vite proxies `/api/*` during development. In production, serve the frontend
# build from the same origin after registering the API routes.
frontend_dist = Path(__file__).resolve().parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

