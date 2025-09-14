
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client
from gpt_db.api.nutrition import DV_DEFAULTS, get_targets


router = APIRouter(prefix="/targets", tags=["targets"])


class TargetUpdates(BaseModel):
    """Payload for partial target updates."""

    model_config = ConfigDict(extra="forbid")

    calories: float | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)


@router.get("", dependencies=[Depends(require_api_key)])
async def get_targets_handler() -> JSONResponse:
    """Return current macro targets."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        targets = await get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.patch("", dependencies=[Depends(require_api_key)])
async def patch_targets(updates: TargetUpdates) -> JSONResponse:
    """Partially update macro targets."""
    data = updates.model_dump(exclude_none=True)
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
        targets = await get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.delete("", dependencies=[Depends(require_api_key)])
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


@router.delete("/{macro}", dependencies=[Depends(require_api_key)])
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
        targets = await get_targets(db)
        return JSONResponse(content={"targets": targets})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )

