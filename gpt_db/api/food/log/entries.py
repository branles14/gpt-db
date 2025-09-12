from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId, errors as bson_errors
from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error, success_response, error_response
from gpt_db.db.mongo import get_mongo_client
from .common import _get_targets


router = APIRouter(prefix="/food", tags=["food"])


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
        return error_response(
            message="Invalid date format", status_code=status.HTTP_400_BAD_REQUEST
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


def _parse_tz_offset(tz: Optional[str]) -> int:
    """Parse a timezone offset string and return minutes offset from UTC.

    Accepts values like "Z", "UTC", "+HH", "+HH:MM", "-HH", "-HHMM".
    Defaults to 0 (UTC) for None or unrecognized inputs.
    """
    if not tz:
        return 0
    tz = tz.strip().upper()
    if tz in {"Z", "UTC", "+0", "+00", "+00:00", "+0000", "-0", "-00", "-00:00", "-0000"}:
        return 0
    sign = 1
    if tz.startswith("+"):
        sign = 1
        tz = tz[1:]
    elif tz.startswith("-"):
        sign = -1
        tz = tz[1:]
    # Accept HH[:MM] or HHMM
    try:
        if ":" in tz:
            hours_str, minutes_str = tz.split(":", 1)
        elif len(tz) > 2:
            hours_str, minutes_str = tz[:2], tz[2:]
        else:
            hours_str, minutes_str = tz, "0"
        hours = int(hours_str or 0)
        minutes = int(minutes_str or 0)
        total = sign * (hours * 60 + minutes)
        # clamp to plausible range
        if total < -14 * 60 or total > 14 * 60:
            return 0
        return total
    except Exception:
        return 0


@router.get("/log/stats", dependencies=[Depends(require_api_key)])
async def get_log_stats(
    start: str = Query(..., description="Start date YYYY-MM-DD (inclusive)"),
    end: str = Query(..., description="End date YYYY-MM-DD (inclusive)"),
    tz: Optional[str] = Query(default=None, description="Timezone offset like +00:00, -08, Z"),
) -> JSONResponse:
    """Return per-day macro totals in a date range.

    - Dates are interpreted in the provided timezone (default UTC).
    - Results are grouped by local date and include an overall sum.
    """
    try:
        # Parse dates
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        if end_date < start_date:
            return error_response(
                message="end must be on/after start",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        offset_min = _parse_tz_offset(tz)
        offset = timedelta(minutes=offset_min)

        # Convert local [start 00:00, end+1 00:00) to UTC instants
        start_local = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_local_next = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)
        # Local to UTC: subtract offset
        start_utc = (start_local - offset).replace(tzinfo=None)
        end_utc = (end_local_next - offset).replace(tzinfo=None)

        client = get_mongo_client()
        db = client.get_database("food")
        log_col = db.get_collection("log")
        catalog_col = db.get_collection("catalog")

        cursor = (
            log_col.find({"timestamp": {"$gte": start_utc, "$lt": end_utc}})
            .sort("timestamp")
        )
        docs = [doc async for doc in cursor]

        # day_totals keyed by YYYY-MM-DD
        day_totals: Dict[str, Dict[str, float]] = {}
        overall = {k: 0.0 for k in ("calories", "protein", "fat", "carbs")}

        for doc in docs:
            product = None
            if doc.get("product_id"):
                product = await catalog_col.find_one({"_id": doc["product_id"]})
            elif doc.get("upc"):
                product = await catalog_col.find_one({"upc": doc["upc"]})
            units = doc.get("units", 1)
            nutrition = (product.get("nutrition") if product else None) or {}
            cals = (nutrition.get("calories") or (product.get("calories") if product else 0) or 0) * units
            prot = (nutrition.get("protein") or (product.get("protein") if product else 0) or 0) * units
            fat = (nutrition.get("fat") or (product.get("fat") if product else 0) or 0) * units
            carbs = (nutrition.get("carbs") or (product.get("carbs") if product else 0) or 0) * units

            # Local-date bucket
            ts = doc.get("timestamp") or datetime.utcnow()
            local_date = (ts + offset).date().isoformat()
            bucket = day_totals.setdefault(local_date, {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0})
            bucket["calories"] += cals
            bucket["protein"] += prot
            bucket["fat"] += fat
            bucket["carbs"] += carbs

            overall["calories"] += cals
            overall["protein"] += prot
            overall["fat"] += fat
            overall["carbs"] += carbs

        days = [
            {"date": d, "totals": {k: round(v, 4) for k, v in t.items()}}
            for d, t in sorted(day_totals.items())
        ]
        return JSONResponse(content={"days": days, "overall": {k: round(v, 4) for k, v in overall.items()}})
    except ValueError:
        return error_response(
            message="Invalid date format", status_code=status.HTTP_400_BAD_REQUEST
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
        return success_response(
            content={"log_id": str(result.inserted_id)},
            message="Log entry created",
            status_code=status.HTTP_201_CREATED,
        )
    except bson_errors.InvalidId:
        return error_response(
            message="Invalid product_id", status_code=status.HTTP_400_BAD_REQUEST
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
            return error_response(
                message="Log entry not found", status_code=status.HTTP_404_NOT_FOUND
            )
        await trash_col.insert_one(doc)
        await log_col.delete_one({"_id": obj_id})
        return success_response(content={"deleted": True}, message="Log entry deleted")
    except bson_errors.InvalidId:
        return error_response(
            message="Invalid log_id", status_code=status.HTTP_400_BAD_REQUEST
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
            return error_response(
                message="No log entries to undo",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        await trash_col.insert_one(doc)
        await log_col.delete_one({"_id": doc["_id"]})
        return success_response(
            content={"deleted_id": str(doc["_id"])},
            message="Last log entry undone",
        )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
