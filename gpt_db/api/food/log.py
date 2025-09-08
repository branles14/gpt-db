from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId, errors as bson_errors
from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client


router = APIRouter(prefix="/food", tags=["food"])


DV_DEFAULTS: Dict[str, float] = {
    "calories": 2000,
    "protein": 50,
    "fat": 78,
    "carbs": 275,
}  # FDA Daily Values for adults and children ≥4 yrs
# Source: https://www.fda.gov/food/new-nutrition-facts-label/daily-value-new-nutrition-and-supplement-facts-labels


async def _get_targets(db) -> Dict[str, float]:
    """Fetch current macro targets, falling back to DV defaults."""
    col = db.get_collection("targets")
    doc = await col.find_one({"_id": "current"})
    if doc:
        doc.pop("_id", None)
        return {**DV_DEFAULTS, **doc}
    return dict(DV_DEFAULTS)


class LogEntry(BaseModel):
    """Payload for appending a log entry manually."""

    product_id: Optional[str] = None
    upc: Optional[str] = None
    units: int = 1
    timestamp: Optional[datetime] = None

    @model_validator(mode="after")
    def _check_identifier(cls, values: "LogEntry") -> "LogEntry":
        if not values.product_id and not values.upc:
            raise ValueError("Either product_id or upc must be provided")
        return values


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo document to JSON-serializable dict."""
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    if "product_id" in result and isinstance(result["product_id"], ObjectId):
        result["product_id"] = str(result["product_id"])
    if "timestamp" in result and isinstance(result["timestamp"], datetime):
        result["timestamp"] = result["timestamp"].isoformat()
    return result


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
    invalid = [k for k in updates if k not in DV_DEFAULTS]
    if invalid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid macro: {invalid[0]}"},
        )
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        col = db.get_collection("targets")
        await col.update_one({"_id": "current"}, {"$set": updates}, upsert=True)
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

@router.get("/log", dependencies=[Depends(require_api_key)])
async def get_log(date: Optional[str] = Query(default=None)) -> JSONResponse:
    """Return log entries for the given date (UTC)."""
    try:
        query_date = (
            datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.utcnow().date()
        )
        start = datetime.combine(query_date, datetime.min.time())
        end = start + timedelta(days=1)
        client = get_mongo_client()
        db = client.get_database("food")
        log_col = db.get_collection("log")
        catalog_col = db.get_collection("catalog")
        targets = await _get_targets(db)
        cursor = (
            log_col.find({"timestamp": {"$gte": start, "$lt": end}})
            .sort("timestamp")
        )
        docs = [doc async for doc in cursor]
        entries: List[Dict[str, Any]] = []
        totals = {k: 0.0 for k in targets}
        for doc in docs:
            product = None
            if doc.get("product_id"):
                product = await catalog_col.find_one({"_id": doc["product_id"]})
            elif doc.get("upc"):
                product = await catalog_col.find_one({"upc": doc["upc"]})
            units = doc.get("units", 1)
            # Support nested nutrition object, fallback to legacy top-level fields
            nutrition = (product.get("nutrition") if product else None) or {}
            calories = (
                (nutrition.get("calories") or (product.get("calories") if product else 0) or 0)
                * units
            )
            protein = (
                (nutrition.get("protein") or (product.get("protein") if product else 0) or 0)
                * units
            )
            fat = (
                (nutrition.get("fat") or (product.get("fat") if product else 0) or 0)
                * units
            )
            carbs = (
                (nutrition.get("carbs") or (product.get("carbs") if product else 0) or 0)
                * units
            )
            totals["calories"] += calories
            totals["protein"] += protein
            totals["fat"] += fat
            totals["carbs"] += carbs
            entries.append(_serialize(doc))
        remaining = {k: max(targets[k] - totals[k], 0) for k in targets}
        return JSONResponse(
            content={"entries": entries, "totals": totals, "remaining": remaining}
        )
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid date format"},
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/log", dependencies=[Depends(require_api_key)])
async def append_log(entry: LogEntry) -> JSONResponse:
    """Append a log entry manually."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("log")
        doc: Dict[str, Any] = {
            "product_id": ObjectId(entry.product_id) if entry.product_id else None,
            "upc": entry.upc,
            "units": entry.units,
            "timestamp": entry.timestamp or datetime.utcnow(),
        }
        result = await collection.insert_one(doc)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"log_id": str(result.inserted_id)},
        )
    except bson_errors.InvalidId:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid product_id"},
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.delete("/log/{log_id}", dependencies=[Depends(require_api_key)])
async def delete_log(log_id: str) -> JSONResponse:
    """Soft delete a log entry by moving it to log_trash."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        log_col = db.get_collection("log")
        trash_col = db.get_collection("log_trash")
        obj_id = ObjectId(log_id)
        doc = await log_col.find_one({"_id": obj_id})
        if not doc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Log entry not found"},
            )
        await trash_col.insert_one(doc)
        await log_col.delete_one({"_id": obj_id})
        return JSONResponse(content={"deleted": True})
    except bson_errors.InvalidId:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid log_id"},
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/log/undo", dependencies=[Depends(require_api_key)])
async def undo_log() -> JSONResponse:
    """Undo the most recent log entry."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        log_col = db.get_collection("log")
        trash_col = db.get_collection("log_trash")
        doc = await log_col.find_one(sort=[("timestamp", -1)])
        if not doc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "No log entries to undo"},
            )
        await trash_col.insert_one(doc)
        await log_col.delete_one({"_id": doc["_id"]})
        return JSONResponse(content={"deleted_id": str(doc["_id"])} )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
