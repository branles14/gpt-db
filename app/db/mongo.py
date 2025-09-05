from typing import Any

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.env import get_mongo_uri

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
        _mongo_client = AsyncIOMotorClient(uri, appname="gpt-db")
    return _mongo_client

