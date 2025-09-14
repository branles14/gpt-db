from typing import Any, Dict, List, Optional
import re

from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import JSONResponse
from bson import ObjectId, errors as bson_errors
import json
from pydantic import BaseModel, Field, model_validator, field_validator, ValidationError
from pydantic.config import ConfigDict

from gpt_db.api.deps import require_api_key
from gpt_db.api.utils import format_mongo_error, success_response, error_response
from gpt_db.db.mongo import get_mongo_client

router = APIRouter(prefix="/catalog", tags=["catalog"])


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

    model_config = ConfigDict(extra="forbid")

    # Energy
    calories: float = Field(default=0, ge=0)

    # Macros (g)
    protein: float = Field(default=0, ge=0)
    fat: float = Field(default=0, ge=0)
    carbs: float = Field(default=0, ge=0)
    fiber: float = Field(default=0, ge=0)
    sugars: float = Field(default=0, ge=0)
    saturated_fat: float = Field(default=0, ge=0)
    trans_fat: float = Field(default=0, ge=0)

    # Cholesterol and electrolytes
    cholesterol_mg: float = Field(default=0, ge=0)
    sodium_mg: float = Field(default=0, ge=0)
    potassium_mg: float = Field(default=0, ge=0)

    # Minerals (mg unless mcg specified)
    calcium_mg: float = Field(default=0, ge=0)
    iron_mg: float = Field(default=0, ge=0)
    magnesium_mg: float = Field(default=0, ge=0)
    phosphorus_mg: float = Field(default=0, ge=0)
    zinc_mg: float = Field(default=0, ge=0)
    selenium_mcg: float = Field(default=0, ge=0)
    copper_mg: float = Field(default=0, ge=0)
    manganese_mg: float = Field(default=0, ge=0)

    # Vitamins (common forms)
    vitamin_a_mcg: float = Field(default=0, ge=0)
    vitamin_c_mg: float = Field(default=0, ge=0)
    vitamin_d_mcg: float = Field(default=0, ge=0)
    vitamin_e_mg: float = Field(default=0, ge=0)
    vitamin_k_mcg: float = Field(default=0, ge=0)
    thiamin_mg: float = Field(default=0, ge=0)  # B1
    riboflavin_mg: float = Field(default=0, ge=0)  # B2
    niacin_mg: float = Field(default=0, ge=0)  # B3
    vitamin_b6_mg: float = Field(default=0, ge=0)
    folate_mcg: float = Field(default=0, ge=0)
    vitamin_b12_mcg: float = Field(default=0, ge=0)


class ProductBase(BaseModel):
    """Shared fields and validators for product models."""

    model_config = ConfigDict(extra="forbid")

    # Common fields (optional by default; creation model will require name)
    name: Optional[str] = None
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
    def _merge_top_level_macros(self) -> "ProductBase":
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

    @field_validator("upc", mode="before")
    @classmethod
    def _validate_upc(cls, v: Any) -> Optional[str]:
        """Ensure UPC is a string of digits. Leading zeros are significant.

        - Reject non-string inputs to avoid lossy coercion (e.g., dropping leading zeros).
        - Trim whitespace and allow empty to become None.
        - Enforce digits-only when provided.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("UPC must be a string with quotes in JSON (digits only)")
        s = v.strip()
        if not s:
            return None
        if not s.isdigit():
            raise ValueError("UPC must contain digits only (0-9)")
        return s


class ProductCreate(ProductBase):
    """Product payload for creation/upsert when creating a new record.

    Requires `name`. `upc` is optional but recommended.
    """

    name: str  # override to required


class ProductUpdate(ProductBase):
    """Product payload for partial update.

    All fields optional; omitted fields are left unchanged. Explicit `null`
    clears the field.
    """
    pass


@router.get("", dependencies=[Depends(require_api_key)])
async def list_products(
    q: Optional[str] = Query(default=None),
    upc: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> JSONResponse:
    """List products with optional filters.

    Behavior:
    - `q` performs a case-insensitive search across `name`, `upc`, `tags`, and
      `ingredients`. The query string is escaped to avoid invalid regex input.
    - `upc` matches exact UPC.
    - `tag` matches case-insensitively within the `tags` array.
    """
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("catalog")

        clauses: List[Dict[str, Any]] = []

        if upc:
            clauses.append({"upc": upc})

        if tag:
            pattern = re.escape(tag)
            clauses.append({"tags": {"$elemMatch": {"$regex": pattern, "$options": "i"}}})

        if q:
            pattern = re.escape(q)
            or_clauses = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"upc": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$elemMatch": {"$regex": pattern, "$options": "i"}}},
                {"ingredients": {"$elemMatch": {"$regex": pattern, "$options": "i"}}},
            ]
            clauses.append({"$or": or_clauses})

        filters: Dict[str, Any]
        if not clauses:
            filters = {}
        elif len(clauses) == 1:
            filters = clauses[0]
        else:
            filters = {"$and": clauses}

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


def _flatten_for_update(
    data: Dict[str, Any],
    parent: str = "",
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Flatten a nested dict into Mongo `$set` and `$unset` ops.

    - Dicts are flattened into dotted paths for `$set`.
    - Lists/primitives are set as-is.
    - `None` values generate `$unset` entries (value is "").
    """
    set_ops: Dict[str, Any] = {}
    unset_ops: Dict[str, str] = {}

    for key, value in data.items():
        if key == "_id":
            continue
        path = f"{parent}.{key}" if parent else key
        if value is None:
            unset_ops[path] = ""
        elif isinstance(value, dict):
            # If dict is empty after excluding None-only entries, it becomes an unset
            sub_set, sub_unset = _flatten_for_update(value, path)
            set_ops.update(sub_set)
            unset_ops.update(sub_unset)
            # If dict had only unsets and no sets, do nothing more; Mongo will
            # remove subfields via $unset paths
        else:
            set_ops[path] = value

    return set_ops, unset_ops


@router.post("", dependencies=[Depends(require_api_key)])
async def upsert_product(payload: Dict[str, Any]) -> JSONResponse:
    """Create or update a product.

    Behavior
    - If `upc` is provided and an item exists: perform a partial merge update.
      Only provided fields are changed; sending `null` explicitly clears a field.
    - Otherwise: create a new product (requires `name`).
    """
    try:
        client = get_mongo_client()
        collection = client.get_database("food").get_collection("catalog")
        upc = payload.get("upc")

        def build_nutrition(p: Dict[str, Any]) -> Dict[str, Any]:
            """Return a full NutritionFacts dict with zeros for missing fields."""
            nutrition_data: Dict[str, Any] = dict(p.get("nutrition") or {})
            for m in ("calories", "protein", "fat", "carbs"):
                if m in p:
                    nutrition_data[m] = p[m]
            unset_fields = {k for k, v in nutrition_data.items() if v is None}
            clean = {k: v for k, v in nutrition_data.items() if v is not None}
            facts = NutritionFacts(**clean).model_dump()
            for k in unset_fields:
                facts[k] = None
            return facts

        if upc:
            # Does a product with this UPC already exist?
            existing = await collection.find_one({"upc": upc})
            if existing:
                # Validate as partial update (also merges top-level macros)
                parsed = ProductUpdate(**payload)

                # Build a normalized dict containing ONLY keys the client provided.
                normalized: Dict[str, Any] = {}
                provided_keys = set(payload.keys())

                # Handle known fields via parsed model to apply normalization
                if "name" in provided_keys:
                    normalized["name"] = parsed.name
                if "upc" in provided_keys:
                    normalized["upc"] = parsed.upc
                if "tags" in provided_keys:
                    normalized["tags"] = parsed.tags
                if "ingredients" in provided_keys:
                    normalized["ingredients"] = parsed.ingredients

                # Handle nutrition and top-level macro aliases
                macros = {k for k in ("calories", "protein", "fat", "carbs") if k in provided_keys}
                if "nutrition" in provided_keys and payload.get("nutrition") is None:
                    normalized["nutrition"] = None
                elif "nutrition" in provided_keys or macros:
                    normalized["nutrition"] = build_nutrition(payload)

                # Preserve any other extra fields exactly as provided
                known = {"name", "upc", "tags", "ingredients", "nutrition", "calories", "protein", "fat", "carbs"}
                for k in provided_keys - known:
                    normalized[k] = payload[k]

                # Build $set/$unset from provided fields only
                set_ops, unset_ops = _flatten_for_update(normalized)
                # If no effective changes, return current doc
                if not set_ops and not unset_ops:
                    return success_response(
                        content={"item": _serialize(existing)},
                        message="Product updated",
                        status_code=status.HTTP_200_OK,
                    )
                update_doc: Dict[str, Any] = {}
                if set_ops:
                    update_doc["$set"] = set_ops
                if unset_ops:
                    update_doc["$unset"] = unset_ops

                result = await collection.update_one({"upc": upc}, update_doc)
                doc = await collection.find_one({"upc": upc})
                if not result.acknowledged or not doc:
                    return error_response(
                        message="Failed to persist product",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                return success_response(
                    content={"item": _serialize(doc)},
                    message="Product updated",
                    status_code=status.HTTP_200_OK,
                )

        # Create path: validate with creation model (requires name)
        data = ProductCreate(**payload).model_dump(exclude_none=True)
        data["nutrition"] = build_nutrition(payload)
        result = await collection.insert_one(data)
        doc = await collection.find_one({"_id": result.inserted_id})
        if not result.acknowledged or not doc:
            return error_response(
                message="Failed to persist product",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return success_response(
            content={"item": _serialize(doc)},
            message="Product created",
            status_code=status.HTTP_201_CREATED,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(e.json()),
        )
    except HTTPException:
        raise
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )


@router.get("/{product_id}", dependencies=[Depends(require_api_key)])
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


@router.delete("/{product_id}", dependencies=[Depends(require_api_key)])
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
                return error_response(
                    message=(
                        "Product is referenced by stock or log; use force=true to delete"
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        result = await db.get_collection("catalog").delete_one({"_id": obj_id})
        if result.deleted_count == 0:
            return error_response(
                message="Product not found", status_code=status.HTTP_404_NOT_FOUND
            )
        return success_response(content={"deleted": True}, message="Product deleted")
    except bson_errors.InvalidId:
        return error_response(
            message="Invalid product_id", status_code=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        content = format_mongo_error(e)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=content
        )
