import asyncio
from typing import Dict

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

from gpt_db.core.env import get_mongo_uri

# Cache clients per running asyncio event loop. This avoids reusing a client
# across different loops (common in serverless), which causes runtime errors.
_clients_by_loop: Dict[int, AsyncIOMotorClient] = {}


def get_mongo_client() -> AsyncIOMotorClient:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    client = _clients_by_loop.get(loop_id)
    if client is None:
        uri = get_mongo_uri()
        if not uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server not configured: set MONGO_URI",
            )
        # Use MongoDB Stable API v1 for compatibility with Atlas strict clusters
        client = AsyncIOMotorClient(
            uri,
            appname="gpt-db",
            server_api=ServerApi("1"),
        )
        _clients_by_loop[loop_id] = client
    return client


def close_mongo_client() -> None:
    """Close and reset all cached MongoDB clients."""
    for client in list(_clients_by_loop.values()):
        try:
            client.close()
        except Exception:
            pass
    _clients_by_loop.clear()


async def ensure_indexes() -> None:
    """Create commonly-used indexes if they don't exist.

    Best-effort: failures are silently ignored so startup does not fail on
    clusters without createIndex privileges.
    """
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        # Catalog: unique UPC when present
        await db.get_collection("catalog").create_index(
            "upc", name="uniq_upc", unique=True, sparse=True
        )
        # Stock: quick lookups by upc/uuid
        await db.get_collection("stock").create_index("upc")
        await db.get_collection("stock").create_index("uuid")
        # Log: sort/range by timestamp
        await db.get_collection("log").create_index("timestamp")
    except Exception:
        # Non-fatal — continue without enforcing indexes
        pass
