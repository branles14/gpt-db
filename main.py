import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)

# Read API_KEY; if missing, don't crash in serverless envs.
API_KEY = os.getenv("API_KEY") or None

# Ensure PORT is an int for uvicorn
PORT = int(os.getenv("PORT", "8000"))

app = FastAPI(title="gpt-db")

# MongoDB client (initialized lazily)
_mongo_client: AsyncIOMotorClient | None = None


def _build_mongo_uri() -> str | None:
    uri = os.getenv("MONGO_URI")
    if uri:
        return uri


def _get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        uri = _build_mongo_uri()
        if not uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server not configured: set MONGO_URI",
            )
        _mongo_client = AsyncIOMotorClient(uri, appname="gpt-db")
    return _mongo_client

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server not configured: set API_KEY")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/list")
async def list_collections(_: None = Depends(require_api_key)) -> JSONResponse:
    """Return list of collections for all accessible databases.

    Response format:
    { "databases": [ {"name": str, "collections": [str, ...]}, ... ] }
    On failure to connect, returns 503 with error info.
    """
    try:
        client = _get_mongo_client()

        # Verify connectivity quickly
        await client.admin.command("ping")

        db_names: List[str] = await client.list_database_names()
        result: List[Dict[str, Any]] = []
        for db_name in db_names:
            # Skip internal DBs commonly present
            if db_name in {"admin", "local", "config"}:
                continue
            db = client.get_database(db_name)
            try:
                colls = await db.list_collection_names()
            except Exception as e:  # If a DB denies access, continue
                colls = []
            result.append({"name": db_name, "collections": sorted(colls)})

        return JSONResponse(content={"databases": result})
    except HTTPException:
        # Re-raise configuration errors
        raise
    except Exception as e:
        # Connection or other runtime failures
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Failed to connect to MongoDB", "reason": str(e)},
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
