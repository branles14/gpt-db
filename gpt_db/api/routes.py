from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from gpt_db.api.food import router as food_router
from gpt_db.api.health import router as health_router
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client

router = APIRouter()
router.include_router(food_router)  # includes stock and catalog
router.include_router(health_router)


@router.get("/", dependencies=[Depends(require_api_key)])
async def root():
    return {"message": "🍌"}


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
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )

