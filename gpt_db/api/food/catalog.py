from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from bson import ObjectId, errors as bson_errors
from pydantic import BaseModel
from pydantic.config import ConfigDict

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error
from gpt_db.db.mongo import get_mongo_client

router = APIRouter(prefix="/food", tags=["food"])


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo document to JSON-serializable dict."""
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


class Product(BaseModel):
    """Product payload for catalog upsert."""

    model_config = ConfigDict(extra="allow")

    name: str
    upc: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("/catalog", dependencies=[Depends(require_api_key)])
async def list_products(
    q: Optional[str] = Query(default=None),
    upc: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> JSONResponse:
    """List products with optional filters."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("catalog")
        filters: Dict[str, Any] = {}
        if q:
            filters["name"] = {"$regex": q, "$options": "i"}
        if upc:
            filters["upc"] = upc
        if tag:
            filters["tags"] = tag
        docs = await collection.find(filters).to_list(length=None)
        items = [_serialize(doc) for doc in docs]
        return JSONResponse(content={"items": items})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/catalog", dependencies=[Depends(require_api_key)])
async def upsert_product(product: Product) -> JSONResponse:
    """Create or update a product by UPC."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("catalog")
        payload = product.model_dump(exclude_none=True)
        if "upc" in payload:
            await collection.update_one(
                {"upc": payload["upc"]}, {"$set": payload}, upsert=True
            )
            doc = await collection.find_one({"upc": payload["upc"]})
        else:
            result = await collection.insert_one(payload)
            doc = await collection.find_one({"_id": result.inserted_id})
        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content={"item": _serialize(doc)}
        )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.get("/catalog/{product_id}", dependencies=[Depends(require_api_key)])
async def get_product(product_id: str) -> JSONResponse:
    """Retrieve a product by its ID."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("catalog")
        doc = await collection.find_one({"_id": ObjectId(product_id)})
        if not doc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Product not found"},
            )
        return JSONResponse(content=_serialize(doc))
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


@router.delete("/catalog/{product_id}", dependencies=[Depends(require_api_key)])
async def delete_product(product_id: str, force: bool = False) -> JSONResponse:
    """Delete a product if not referenced by stock or log unless forced."""
    try:
        client = get_mongo_client()
        db = client.get_database("food")
        obj_id = ObjectId(product_id)

        if not force:
            stock_count = await db.get_collection("stock").count_documents(
                {"product_id": obj_id}
            )
            log_count = await db.get_collection("log").count_documents(
                {"product_id": obj_id}
            )
            if stock_count > 0 or log_count > 0:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": "Product is referenced by stock or log; use force=true to delete",
                    },
                )

        result = await db.get_collection("catalog").delete_one({"_id": obj_id})
        if result.deleted_count == 0:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Product not found"},
            )
        return JSONResponse(content={"deleted": True})
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
