from typing import Dict

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client
from .common import DV_DEFAULTS, _get_targets


router = APIRouter(prefix="/food", tags=["food"])


@router.get("/targets", dependencies=[Depends(require_api_key)])
async def get_targets() -> JSONResponse:
    """Return current macro targets."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        targets = await _get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.patch("/targets", dependencies=[Depends(require_api_key)])
async def patch_targets(updates: Dict[str, float]) -> JSONResponse:
    """Partially update macro targets."""
    # Simple validation: non-negative numbers for known keys
    data: Dict[str, float] = {
        k: float(v)
        for k, v in updates.items()
        if k in DV_DEFAULTS and isinstance(v, (int, float)) and float(v) >= 0
    }
    if not data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "No valid fields provided"},
        )
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        col = db.get_collection("targets")
        await col.update_one({"_id": "current"}, {"$set": data}, upsert=True)
        targets = await _get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.delete("/targets", dependencies=[Depends(require_api_key)])
async def delete_targets() -> JSONResponse:
    """Reset all targets to defaults."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        col = db.get_collection("targets")
        await col.delete_many({})
        return JSONResponse(content={"targets": dict(DV_DEFAULTS)})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.delete("/targets/{macro}", dependencies=[Depends(require_api_key)])
async def delete_target_macro(macro: str) -> JSONResponse:
    """Reset a single macro to its default."""
    if macro not in DV_DEFAULTS:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Unknown macro"},
        )
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        col = db.get_collection("targets")
        await col.update_one({"_id": "current"}, {"$unset": {macro: ""}})
        targets = await _get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )

