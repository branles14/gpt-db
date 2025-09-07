from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId, errors as bson_errors
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, root_validator

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client


router = APIRouter(prefix="/food", tags=["food"])


DAILY_TARGETS: Dict[str, float] = {
    "calories": 2000,
    "protein": 150,
    "fat": 70,
    "carbs": 250,
}


class LogEntry(BaseModel):
    """Payload for appending a log entry manually."""

    product_id: Optional[str] = None
    upc: Optional[str] = None
    units: int = 1
    timestamp: Optional[datetime] = None

    @root_validator
    def _check_identifier(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not values.get("product_id") and not values.get("upc"):
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
        docs = (
            await log_col.find({"timestamp": {"$gte": start, "$lt": end}})
            .sort("timestamp")
            .to_list(length=None)
        )
        entries: List[Dict[str, Any]] = []
        totals = {k: 0.0 for k in DAILY_TARGETS}
        for doc in docs:
            product = None
            if doc.get("product_id"):
                product = await catalog_col.find_one({"_id": doc["product_id"]})
            elif doc.get("upc"):
                product = await catalog_col.find_one({"upc": doc["upc"]})
            units = doc.get("units", 1)
            calories = (product.get("calories", 0) if product else 0) * units
            protein = (product.get("protein", 0) if product else 0) * units
            fat = (product.get("fat", 0) if product else 0) * units
            carbs = (product.get("carbs", 0) if product else 0) * units
            totals["calories"] += calories
            totals["protein"] += protein
            totals["fat"] += fat
            totals["carbs"] += carbs
            entries.append(_serialize(doc))
        remaining = {k: max(DAILY_TARGETS[k] - totals[k], 0) for k in DAILY_TARGETS}
        return JSONResponse(
            content={"entries": entries, "totals": totals, "remaining": remaining}
        )
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid date format"},
        )
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

