"""IncidentMind AI FastAPI application entry point."""

from fastapi import FastAPI

from backend.api import router
from config.logging import configure_logging

configure_logging()

app = FastAPI(title="IncidentMind AI", version="0.1.0")
app.include_router(router)

