from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import require_api_key
from app.db.mongo import get_mongo_client

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "ok"}


@router.get("/list")
async def list_collections(_: None = Depends(require_api_key)) -> JSONResponse:
    """Return list of collections for all accessible databases.

    Response format:
    { "databases": [ {"name": str, "collections": [str, ...]}, ... ] }
    On failure to connect, returns 503 with error info.
    """
    try:
        client = get_mongo_client()

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
            except Exception:
                # If a DB denies access, continue
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

