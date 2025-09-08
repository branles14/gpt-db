from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId, errors as bson_errors
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator
from pymongo import ReturnDocument

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client

router = APIRouter(prefix="/food", tags=["food"])


class StockItem(BaseModel):
    """Payload for adding stock units."""

    product_id: Optional[str] = None
    upc: Optional[str] = None
    quantity: int

    @model_validator(mode="after")
    def _check_identifier(cls, values: "StockItem") -> "StockItem":
        if not values.product_id and not values.upc:
            raise ValueError("Either product_id or upc must be provided")
        return values


class AddStockRequest(BaseModel):
    """Request wrapper for adding stock units."""

    items: List[StockItem]


class ConsumeItem(BaseModel):
    """Payload for consuming or removing stock."""

    product_id: Optional[str] = None
    upc: Optional[str] = None
    units: int = 1
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _check_identifier(cls, values: "ConsumeItem") -> "ConsumeItem":
        if not values.product_id and not values.upc:
            raise ValueError("Either product_id or upc must be provided")
        return values


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo document to JSON-serializable dict."""
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


@router.get("/stock", dependencies=[Depends(require_api_key)])
async def get_food_stock(
    view: str = Query("aggregate", enum=["aggregate", "items"])
) -> JSONResponse:
    """Return stock in aggregated or per-item views."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        if view == "items":
            docs = await collection.find().to_list(length=None)
            items = [_serialize(doc) for doc in docs]
        else:
            pipeline = [
                {
                    "$group": {
                        "_id": {"product_id": "$product_id", "upc": "$upc"},
                        "quantity": {"$sum": "$quantity"},
                    }
                }
            ]
            docs = await collection.aggregate(pipeline).to_list(length=None)
            items = [
                {
                    "product_id": (
                        str(doc["_id"].get("product_id"))
                        if doc["_id"].get("product_id")
                        else None
                    ),
                    "upc": doc["_id"].get("upc"),
                    "quantity": doc.get("quantity", 0),
                }
                for doc in docs
            ]
        return JSONResponse(content={"items": items})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/stock", dependencies=[Depends(require_api_key)])
async def add_food_stock(payload: AddStockRequest) -> JSONResponse:
    """Add stock units for one or more products."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        upserted_ids: List[str] = []
        for item in payload.items:
            filter: Dict[str, Any]
            if item.product_id:
                filter = {"product_id": ObjectId(item.product_id)}
            else:
                filter = {"upc": item.upc}
            result = await collection.update_one(
                filter,
                {"$inc": {"quantity": item.quantity}},
                upsert=True,
            )
            if result.upserted_id:
                upserted_ids.append(str(result.upserted_id))
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"upserted_ids": upserted_ids},
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


@router.post("/stock/consume", dependencies=[Depends(require_api_key)])
async def consume_stock(item: ConsumeItem) -> JSONResponse:
    """Atomically decrement stock and log consumption."""
    if item.reason is not None:
        # reason is not used for consume; ignore if provided
        item.reason = None
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        stock_col = db.get_collection("stock")
        log_col = db.get_collection("log")
        async with await client.start_session() as session:
            async with session.start_transaction():
                filter: Dict[str, Any]
                if item.product_id:
                    filter = {"product_id": ObjectId(item.product_id)}
                else:
                    filter = {"upc": item.upc}
                filter["quantity"] = {"$gte": item.units}
                doc = await stock_col.find_one_and_update(
                    filter,
                    {"$inc": {"quantity": -item.units}},
                    session=session,
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    await session.abort_transaction()
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "Insufficient stock"},
                    )
                await log_col.insert_one(
                    {
                        "product_id": doc.get("product_id"),
                        "upc": doc.get("upc"),
                        "units": item.units,
                        "timestamp": datetime.utcnow(),
                    },
                    session=session,
                )
        return JSONResponse(content={"remaining": doc["quantity"]})
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


@router.post("/stock/remove", dependencies=[Depends(require_api_key)])
async def remove_stock(item: ConsumeItem) -> JSONResponse:
    """Decrement stock without nutritional logging."""
    if not item.reason:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "reason is required"},
        )
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        stock_col = db.get_collection("stock")
        removal_col = db.get_collection("stock_removals")
        async with await client.start_session() as session:
            async with session.start_transaction():
                filter: Dict[str, Any]
                if item.product_id:
                    filter = {"product_id": ObjectId(item.product_id)}
                else:
                    filter = {"upc": item.upc}
                filter["quantity"] = {"$gte": item.units}
                doc = await stock_col.find_one_and_update(
                    filter,
                    {"$inc": {"quantity": -item.units}},
                    session=session,
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    await session.abort_transaction()
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "Insufficient stock"},
                    )
                await removal_col.insert_one(
                    {
                        "product_id": doc.get("product_id"),
                        "upc": doc.get("upc"),
                        "units": item.units,
                        "reason": item.reason,
                        "timestamp": datetime.utcnow(),
                    },
                    session=session,
                )
        return JSONResponse(content={"remaining": doc["quantity"]})
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


@router.delete("/stock/{stock_id}", dependencies=[Depends(require_api_key)])
async def delete_stock_row(stock_id: str) -> JSONResponse:
    """Delete a specific stock document by ID."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        result = await collection.delete_one({"_id": ObjectId(stock_id)})
        if result.deleted_count == 0:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Stock item not found"},
            )
        return JSONResponse(content={"deleted": True})
    except bson_errors.InvalidId:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid stock_id"},
        )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
