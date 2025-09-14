from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional
import logging

from bson import ObjectId, errors as bson_errors
from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict
from pymongo import ReturnDocument

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error, success_response, error_response
from gpt_db.db.mongo import get_mongo_client
from gpt_db.api.catalog import NutritionFacts, NutritionBreakdown
from gpt_db.api.openfoodfacts import fetch_product

router = APIRouter(prefix="/stock", tags=["stock"])


class StockItem(BaseModel):
    """Payload for adding stock units with optional metadata to sync to catalog.

    Adding to stock requires a UPC. product_id is not accepted here.
    """

    model_config = ConfigDict(extra="allow")

    upc: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    # Optional enrichment fields that may also update catalog
    name: Optional[str] = None
    tags: Optional[List[str]] = Field(default=None, min_length=1)
    ingredients: Optional[List[str]] = Field(default=None, min_length=1)
    nutrition: Optional[NutritionBreakdown] = None

    @field_validator("upc", mode="before")
    @classmethod
    def _validate_upc(cls, v: Any) -> str:
        """Ensure UPC is a quoted string of digits.

        This mirrors catalog validation so that items seeded via stock never
        create catalog rows with malformed UPCs (e.g., numbers that drop leading
        zeros, spaces, or hyphens)."""
        if not isinstance(v, str):
            raise TypeError("UPC must be a string with quotes in JSON (digits only)")
        s = v.strip()
        if not s or not s.isdigit():
            raise ValueError("UPC must contain digits only (0-9)")
        return s

    @field_validator("tags", "ingredients", mode="before")
    @classmethod
    def _normalize_string_list(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            try:
                v = list(v)  # type: ignore[arg-type]
            except Exception:
                raise TypeError("Expected a string or list of strings")
        seen: set[str] = set()
        result: List[str] = []
        for item in v:
            s = str(item).strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            result.append(s)
        return result or None


class AddStockRequest(BaseModel):
    """Request wrapper for adding stock units."""

    items: List[StockItem]


class ConsumeItem(BaseModel):
    """Payload for consuming or removing stock (UPC-only)."""

    upc: str = Field(min_length=1)
    units: int = Field(default=1, gt=0)
    reason: Optional[str] = None


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo document to JSON-serializable dict.

    Stock documents expose "uuid" as the identifier and do not leak Mongo _id.
    """
    result = dict(doc)
    # Ensure uuid is a string output; do not expose _id
    if "uuid" in result and isinstance(result["uuid"], (bytes, bytearray)):
        result["uuid"] = result["uuid"].decode()
    if "_id" in result:
        # Do not include Mongo's _id in API responses
        result.pop("_id", None)
    # Normalize product_id to string if present
    if "product_id" in result and isinstance(result["product_id"], ObjectId):
        result["product_id"] = str(result["product_id"])
    return result


@router.get("", dependencies=[Depends(require_api_key)])
async def get_food_stock(
    view: str = Query("aggregate", enum=["aggregate", "items"])
) -> JSONResponse:
    """Return stock in aggregated or per-item views."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        if view == "items":
            cursor = collection.find()
            items: List[Dict[str, Any]] = []
            async for doc in cursor:
                if not doc.get("uuid"):
                    new_uuid = str(uuid4())
                    await collection.update_one({"_id": doc["_id"]}, {"$set": {"uuid": new_uuid}})
                    doc["uuid"] = new_uuid
                items.append(_serialize(doc))
        else:
            pipeline = [
                {
                    "$group": {
                        "_id": {"product_id": "$product_id", "upc": "$upc"},
                        "quantity": {"$sum": "$quantity"},
                    }
                }
            ]
            agg_cursor = collection.aggregate(pipeline)
            items = []
            async for doc in agg_cursor:
                items.append(
                    {
                        "product_id": (
                            str(doc["_id"].get("product_id"))
                            if doc["_id"].get("product_id")
                            else None
                        ),
                        "upc": doc["_id"].get("upc"),
                        "quantity": doc.get("quantity", 0),
                    }
                )
        return JSONResponse(content={"items": items})
    except HTTPException:
        # Propagate config/auth errors verbatim
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("", dependencies=[Depends(require_api_key)])
async def add_food_stock(payload: AddStockRequest) -> JSONResponse:
    """Add stock units for one or more products."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        collection = db.get_collection("stock")
        catalog = db.get_collection("catalog")
        upserted_uuids: List[str] = []
        for item in payload.items:
            filter: Dict[str, Any]
            set_fields: Dict[str, Any] = {}
            product_doc: Optional[Dict[str, Any]] = None

            # Using UPC; try to inherit fields from catalog
            filter = {"upc": item.upc}
            product_doc = await catalog.find_one({"upc": item.upc})

            if not product_doc:
                try:
                    fetched = await fetch_product(item.upc)
                except Exception as exc:  # pragma: no cover - network errors
                    logging.warning(
                        "OpenFoodFacts lookup failed for %s: %s", item.upc, exc
                    )
                    fetched = None
                if fetched:
                    try:
                        await catalog.update_one(
                            {"upc": item.upc},
                            {"$set": {"upc": item.upc, **fetched}},
                            upsert=True,
                        )
                        product_doc = await catalog.find_one({"upc": item.upc})
                    except Exception as exc:  # pragma: no cover - db errors
                        logging.warning(
                            "Failed to upsert OpenFoodFacts data for %s: %s",
                            item.upc,
                            exc,
                        )

            # Sync provided metadata into catalog based on UPC
            if item.upc:
                item_data = item.model_dump(exclude_none=True)

                # Build incoming nutrition (prefer nested; merge any top-level macros provided as extras)
                incoming_nutrition: Dict[str, Any] | None = None
                if "nutrition" in item_data:
                    incoming_nutrition = dict(item_data["nutrition"])  # type: ignore[arg-type]
                macro_keys = ("calories", "protein", "fat", "carbs", "fiber", "sugars")
                macro_payload = {
                    k: item_data[k]
                    for k in macro_keys
                    if k in item_data and item_data[k] is not None
                }
                if macro_payload:
                    ps = dict((incoming_nutrition or {}).get("per_serving") or {})
                    ps.update(macro_payload)
                    incoming_nutrition = {**(incoming_nutrition or {}), "per_serving": ps}

                if product_doc:
                    # Prepare $set updates only when values change or extend existing arrays
                    catalog_set: Dict[str, Any] = {}
                    if "name" in item_data and item_data["name"] and item_data["name"] != product_doc.get("name"):
                        catalog_set["name"] = item_data["name"]

                    def union(existing: Optional[List[str]], new_list: Optional[List[str]]) -> Optional[List[str]]:
                        if new_list is None:
                            return None
                        existing_list = [str(x) for x in (existing or [])]
                        merged: List[str] = []
                        seen: set[str] = set()
                        for s in existing_list + [str(x) for x in new_list]:
                            t = s.strip()
                            key = t.lower()
                            if not t or key in seen:
                                continue
                            seen.add(key)
                            merged.append(t)
                        if merged != existing_list:
                            return merged
                        return None

                    tags_union = union(product_doc.get("tags"), item_data.get("tags"))
                    if tags_union is not None:
                        catalog_set["tags"] = tags_union
                    ingredients_union = union(product_doc.get("ingredients"), item_data.get("ingredients"))
                    if ingredients_union is not None:
                        catalog_set["ingredients"] = ingredients_union

                    if incoming_nutrition:
                        existing_nutrition = product_doc.get("nutrition") or {}
                        merged_nutrition = existing_nutrition.copy()
                        for key, value in incoming_nutrition.items():
                            if key in ("per_serving", "per_100g", "per_container") and isinstance(value, dict):
                                merged = {**existing_nutrition.get(key, {}), **value}
                                merged_nutrition[key] = merged
                            else:
                                merged_nutrition[key] = value
                        if merged_nutrition != existing_nutrition:
                            catalog_set["nutrition"] = merged_nutrition

                    if catalog_set:
                        await catalog.update_one({"_id": product_doc["_id"]}, {"$set": catalog_set})
                        product_doc = await catalog.find_one({"_id": product_doc["_id"]})
                else:
                    # Create a new catalog item using whatever details were provided
                    new_doc: Dict[str, Any] = {"upc": item.upc}
                    for key in ("name", "tags", "ingredients"):
                        if key in item_data:
                            new_doc[key] = item_data[key]
                    if incoming_nutrition:
                        new_doc["nutrition"] = incoming_nutrition
                    # Even if only UPC is provided, seed the catalog for fast future adds
                    await catalog.update_one({"upc": item.upc}, {"$set": new_doc}, upsert=True)
                    product_doc = await catalog.find_one({"upc": item.upc})

            if product_doc:
                # Build a snapshot of product fields to store on stock
                set_fields["product_id"] = product_doc.get("_id")
                # Primitive fields
                for key in ("upc", "name", "tags", "ingredients"):
                    if key in product_doc:
                        set_fields[key] = product_doc[key]
                # Nutrition: prefer nested object, else synthesize from top-level macros
                nutrition = product_doc.get("nutrition") or {}
                if not nutrition:
                    macros = {
                        k: product_doc[k]
                        for k in ("calories", "protein", "fat", "carbs", "fiber", "sugars")
                        if product_doc.get(k) is not None
                    }
                    if macros:
                        nutrition = {"per_serving": macros}
                if nutrition:
                    set_fields["nutrition"] = nutrition

            update_doc: Dict[str, Any] = {
                "$inc": {"quantity": item.quantity},
                "$setOnInsert": {"uuid": str(uuid4())},
            }
            if set_fields:
                update_doc["$set"] = set_fields

            result = await collection.update_one(
                filter,
                update_doc,
                upsert=True,
            )
            # Fetch the latest document to get its uuid (and backfill if missing)
            doc = await collection.find_one(filter)
            if doc and not doc.get("uuid"):
                new_uuid = str(uuid4())
                await collection.update_one(filter, {"$set": {"uuid": new_uuid}})
                doc["uuid"] = new_uuid
            if doc and doc.get("uuid"):
                upserted_uuids.append(str(doc.get("uuid")))
        return success_response(
            content={"upserted_uuids": upserted_uuids, "count": len(upserted_uuids)},
            message="Stock updated",
            status_code=status.HTTP_201_CREATED,
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/consume", dependencies=[Depends(require_api_key)])
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
                filter: Dict[str, Any] = {"upc": item.upc}
                filter["quantity"] = {"$gte": item.units}
                doc = await stock_col.find_one_and_update(
                    filter,
                    {"$inc": {"quantity": -item.units}},
                    session=session,
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    await session.abort_transaction()
                    return error_response(
                        message="Insufficient stock",
                        status_code=status.HTTP_400_BAD_REQUEST,
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
        return success_response(content={"remaining": doc["quantity"]}, message="Stock consumed")
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


@router.post("/remove", dependencies=[Depends(require_api_key)])
async def remove_stock(item: ConsumeItem) -> JSONResponse:
    """Decrement stock without nutritional logging."""
    if not item.reason:
        return error_response(
            message="reason is required", status_code=status.HTTP_400_BAD_REQUEST
        )
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        stock_col = db.get_collection("stock")
        removal_col = db.get_collection("stock_removals")
        async with await client.start_session() as session:
            async with session.start_transaction():
                filter: Dict[str, Any] = {"upc": item.upc}
                filter["quantity"] = {"$gte": item.units}
                doc = await stock_col.find_one_and_update(
                    filter,
                    {"$inc": {"quantity": -item.units}},
                    session=session,
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    await session.abort_transaction()
                    return error_response(
                        message="Insufficient stock",
                        status_code=status.HTTP_400_BAD_REQUEST,
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
        return success_response(content={"remaining": doc["quantity"]}, message="Stock removed")
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


@router.delete("/{stock_uuid}", dependencies=[Depends(require_api_key)])
async def delete_stock_row(stock_uuid: str) -> JSONResponse:
    """Delete a specific stock document by its UUID."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        result = await collection.delete_one({"uuid": stock_uuid})
        if result.deleted_count == 0:
            return error_response(
                message="Stock item not found", status_code=status.HTTP_404_NOT_FOUND
            )
        return success_response(content={"deleted": True}, message="Stock item deleted")
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
