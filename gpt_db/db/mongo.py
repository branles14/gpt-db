from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

from gpt_db.core.env import get_mongo_uri

_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        uri = get_mongo_uri()
        if not uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server not configured: set MONGO_URI",
            )
        # Use MongoDB Stable API v1 for compatibility with Atlas strict clusters
        _mongo_client = AsyncIOMotorClient(
            uri,
            appname="gpt-db",
            server_api=ServerApi("1"),
        )
    return _mongo_client


def close_mongo_client() -> None:
    """Close and reset the cached MongoDB client."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
