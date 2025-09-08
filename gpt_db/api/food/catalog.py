from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import JSONResponse
from bson import ObjectId, errors as bson_errors
from pydantic import BaseModel, Field, model_validator, field_validator
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


class NutritionFacts(BaseModel):
    """Expanded per-unit nutrition facts.

    Units: macros in grams, energy in kcal, most micronutrients in mg or mcg.
    """

    model_config = ConfigDict(extra="allow")

    # Energy
    calories: Optional[float] = Field(default=None, ge=0)

    # Macros (g)
    protein: Optional[float] = Field(default=None, ge=0)
    fat: Optional[float] = Field(default=None, ge=0)
    carbs: Optional[float] = Field(default=None, ge=0)
    fiber: Optional[float] = Field(default=None, ge=0)
    sugars: Optional[float] = Field(default=None, ge=0)
    saturated_fat: Optional[float] = Field(default=None, ge=0)
    trans_fat: Optional[float] = Field(default=None, ge=0)

    # Cholesterol and electrolytes
    cholesterol_mg: Optional[float] = Field(default=None, ge=0)
    sodium_mg: Optional[float] = Field(default=None, ge=0)
    potassium_mg: Optional[float] = Field(default=None, ge=0)

    # Minerals (mg unless mcg specified)
    calcium_mg: Optional[float] = Field(default=None, ge=0)
    iron_mg: Optional[float] = Field(default=None, ge=0)
    magnesium_mg: Optional[float] = Field(default=None, ge=0)
    phosphorus_mg: Optional[float] = Field(default=None, ge=0)
    zinc_mg: Optional[float] = Field(default=None, ge=0)
    selenium_mcg: Optional[float] = Field(default=None, ge=0)
    copper_mg: Optional[float] = Field(default=None, ge=0)
    manganese_mg: Optional[float] = Field(default=None, ge=0)

    # Vitamins (common forms)
    vitamin_a_mcg: Optional[float] = Field(default=None, ge=0)
    vitamin_c_mg: Optional[float] = Field(default=None, ge=0)
    vitamin_d_mcg: Optional[float] = Field(default=None, ge=0)
    vitamin_e_mg: Optional[float] = Field(default=None, ge=0)
    vitamin_k_mcg: Optional[float] = Field(default=None, ge=0)
    thiamin_mg: Optional[float] = Field(default=None, ge=0)  # B1
    riboflavin_mg: Optional[float] = Field(default=None, ge=0)  # B2
    niacin_mg: Optional[float] = Field(default=None, ge=0)  # B3
    vitamin_b6_mg: Optional[float] = Field(default=None, ge=0)
    folate_mcg: Optional[float] = Field(default=None, ge=0)
    vitamin_b12_mcg: Optional[float] = Field(default=None, ge=0)


class Product(BaseModel):
    """Product payload for catalog upsert."""

    model_config = ConfigDict(extra="allow")

    name: str
    upc: Optional[str] = None
    tags: Optional[List[str]] = Field(default=None, min_length=1)
    ingredients: Optional[List[str]] = Field(default=None, min_length=1)

    # Nested nutrition object (preferred)
    nutrition: Optional[NutritionFacts] = None

    # Deprecated: accept top-level macros for backward compatibility
    calories: Optional[float] = Field(default=None, ge=0)
    protein: Optional[float] = Field(default=None, ge=0)
    fat: Optional[float] = Field(default=None, ge=0)
    carbs: Optional[float] = Field(default=None, ge=0)

    @field_validator("tags", "ingredients", mode="before")
    @classmethod
    def _normalize_string_list(cls, v: Any) -> Optional[List[str]]:
        """Normalize list fields to unique, trimmed strings.

        - Accept a single string or list-like input
        - Trim whitespace, drop empty entries
        - De-duplicate case-insensitively while preserving original case
        """
        if v is None:
            return None
        # Allow passing a single string
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            # Coerce other iterables to list of strings if possible
            try:
                v = list(v)  # type: ignore[arg-type]
            except Exception as _:
                raise TypeError("Expected a string or list of strings")
        seen: set[str] = set()
        result: List[str] = []
        for item in v:
            item_str = str(item).strip()
            if not item_str:
                continue
            key = item_str.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(item_str)
        return result or None

    @model_validator(mode="after")
    def _merge_top_level_macros(self) -> "Product":
        """Move any provided top-level macros into the nutrition object."""
        # If nothing provided, skip
        provided = {
            k: v
            for k, v in {
                "calories": self.calories,
                "protein": self.protein,
                "fat": self.fat,
                "carbs": self.carbs,
            }.items()
            if v is not None
        }
        if provided:
            base = self.nutrition.model_dump(exclude_none=True) if self.nutrition else {}
            base.update(provided)
            self.nutrition = NutritionFacts(**base)
            # Clear deprecated top-level fields to avoid storing duplicates
            self.calories = None
            self.protein = None
            self.fat = None
            self.carbs = None
        return self


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
        cursor = collection.find(filters)
        items = [_serialize(doc) async for doc in cursor]
        return JSONResponse(content={"items": items})
    except HTTPException:
        raise
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
        # Dump with deprecated top-level macros removed (merged into nutrition)
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
