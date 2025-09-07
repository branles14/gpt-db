from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import require_api_key
from app.api.utils import format_mongo_error
from app.db.mongo import get_mongo_client

router = APIRouter(prefix="/food", tags=["food"])


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo document to JSON-serializable dict."""
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


@router.get("/stock", dependencies=[Depends(require_api_key)])
async def get_food_stock() -> JSONResponse:
    """Return all items in `food.stock` collection."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        docs = await collection.find().to_list(length=None)
        items = [_serialize(doc) for doc in docs]
        return JSONResponse(content={"items": items})
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.post("/stock", dependencies=[Depends(require_api_key)])
async def add_food_stock(items: List[Dict[str, Any]]) -> JSONResponse:
    """Insert one or more items into `food.stock` collection."""
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("stock")
        result = await collection.insert_many(items)
        ids = [str(_id) for _id in result.inserted_ids]
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"inserted_ids": ids},
        )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
