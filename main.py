"""IncidentMind AI FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

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

