from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient

from gpt_db.core.env import get_mongo_uri


async def mongo_status() -> dict[str, str]:
    """Check MongoDB connectivity.

    Returns a dict with ``status`` set to ``"ok"`` or ``"error"``.
    On error, a ``detail`` field describes the exception.
    """
    client: AsyncIOMotorClient | None = None
    try:
        uri = get_mongo_uri()
        if not uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server not configured: set MONGO_URI",
            )
        client = AsyncIOMotorClient(uri, appname="gpt-db")
        await client.admin.command("ping")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        if client is not None:
            client.close()
