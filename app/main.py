"""FastAPI entrypoint for the notes microservice."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import connect_db, disconnect_db
from app.routers import health, notes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Start serving immediately; connect MongoDB in the background.

    Uvicorn binds even if Atlas is unreachable. On shutdown, cancel the
    reconnect task and close the client cleanly.
    """
    await connect_db()
    try:
        yield
    finally:
        await disconnect_db()


app = FastAPI(
    title="notes-service",
    description="A Python based microservice to perform CRUD operations for notes data",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(notes.router)
