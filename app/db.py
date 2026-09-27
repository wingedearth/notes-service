"""Motor async MongoDB client with resilient background reconnect."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

DbConnectionState = Literal["disconnected", "connecting", "connected", "error"]

INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0
SERVER_SELECTION_TIMEOUT_MS = 5000
PING_INTERVAL_S = 10.0

_client: AsyncIOMotorClient | None = None
_state: DbConnectionState = "disconnected"
_intentional_close = False
_reconnect_task: asyncio.Task | None = None
_connect_attempt = 0


def is_database_ready() -> bool:
    """True when MongoDB is connected and usable for CRUD."""
    return _state == "connected" and _client is not None


def get_database_state() -> DbConnectionState:
    """Coarse connection state for health/readiness reporting."""
    return _state


def _close_client(client: AsyncIOMotorClient | None) -> None:
    if client is None:
        return
    try:
        client.close()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.exception("Error closing MongoDB client")


async def _ensure_indexes(client: AsyncIOMotorClient) -> None:
    settings = get_settings()
    notes = client[settings.db_name]["notes"]
    # Idempotent indexes for user-scoped queries.
    await notes.create_index("userId")
    await notes.create_index([("userId", 1), ("created_at", -1)])


async def _attempt_connect() -> bool:
    """Create client, ping, and ensure indexes. Returns True on success."""
    global _client, _state, _connect_attempt

    if _intentional_close:
        return False

    settings = get_settings()
    _state = "connecting"
    previous = _client
    _client = None
    _close_client(previous)

    client: AsyncIOMotorClient | None = None
    try:
        logger.info(
            "Attempting MongoDB connection (attempt %s)...",
            _connect_attempt + 1,
        )
        client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        )
        await client.admin.command("ping")
        await _ensure_indexes(client)
        _client = client
        client = None  # ownership transferred
        _state = "connected"
        _connect_attempt = 0
        logger.info("MongoDB connected")
        return True
    except Exception as exc:  # noqa: BLE001 — never kill the process on DB failure
        logger.error("Error connecting to MongoDB: %s", exc)
        _state = "error"
        _close_client(client)
        _client = None
        return False


def _mark_lost(reason: str) -> None:
    """Mark connection lost so the maintain loop will reconnect."""
    global _client, _state
    logger.warning("MongoDB connection lost: %s", reason)
    _close_client(_client)
    _client = None
    if not _intentional_close:
        _state = "error"


async def _watch_connection() -> None:
    """Periodically ping while connected; return when the connection drops."""
    while not _intentional_close and is_database_ready():
        try:
            await asyncio.sleep(PING_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        if _intentional_close or not is_database_ready():
            return
        try:
            assert _client is not None
            await _client.admin.command("ping")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _mark_lost(str(exc))
            return


async def _maintain_connection() -> None:
    """Background loop: connect with exponential backoff; re-watch on drop."""
    global _connect_attempt

    while not _intentional_close:
        if is_database_ready():
            await _watch_connection()
            if _intentional_close:
                return
            # Fell through after a drop — continue into reconnect backoff.
        else:
            success = await _attempt_connect()
            if success:
                continue

            _connect_attempt += 1
            backoff = min(
                INITIAL_BACKOFF_S * (2 ** (_connect_attempt - 1)),
                MAX_BACKOFF_S,
            )
            logger.info(
                "Scheduling MongoDB reconnect attempt %s in %.0fms",
                _connect_attempt,
                backoff * 1000,
            )
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise


async def connect_db() -> None:
    """
    Start background MongoDB connect/reconnect.

    Returns immediately. Never raises on connection failure — HTTP can serve
    liveness while the background task retries with exponential backoff.
    """
    global _intentional_close, _reconnect_task, _connect_attempt

    _intentional_close = False
    if _reconnect_task is not None and not _reconnect_task.done():
        return

    _connect_attempt = 0
    _reconnect_task = asyncio.create_task(
        _maintain_connection(),
        name="notes-service-mongo-reconnect",
    )


async def disconnect_db() -> None:
    """Cancel reconnect work and close the Motor client (intentional shutdown)."""
    global _intentional_close, _client, _state, _reconnect_task, _connect_attempt

    _intentional_close = True

    task = _reconnect_task
    _reconnect_task = None
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    _close_client(_client)
    _client = None
    _state = "disconnected"
    _connect_attempt = 0
    logger.info("MongoDB client disconnected")


def get_client() -> AsyncIOMotorClient:
    """Return the active Motor client."""
    if _client is None or not is_database_ready():
        raise RuntimeError("MongoDB client is not connected")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """Return the configured database handle."""
    settings = get_settings()
    return get_client()[settings.db_name]


def get_notes_collection():
    """Return the notes collection."""
    return get_database()["notes"]


async def require_database() -> None:
    """FastAPI dependency: reject DB-backed routes with 503 when Mongo is down."""
    if is_database_ready():
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "unavailable",
            "reason": "database",
            "database": get_database_state(),
            "service": "notes-service",
        },
    )
