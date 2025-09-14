import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


async def fetch_product(upc: str) -> dict | None:
    """Fetch and normalize product data from OpenFoodFacts.

    Returns a dictionary compatible with the catalog schema or ``None`` if the
    product cannot be retrieved.
    """
    url = f"https://world.openfoodfacts.org/api/v2/product/{upc}.json"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # Network or parsing errors
        logger.warning("OpenFoodFacts request failed for %s: %s", upc, exc)
        return None

    if not isinstance(data, dict) or data.get("status") != 1:
        return None

    product = data.get("product") or {}
    result: Dict[str, Any] = {}

    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
    )
    if isinstance(name, str) and name.strip():
        result["name"] = name.strip()

    # Collect tags from categories/labels
    tags: List[str] = []
    for key in ("categories_tags", "labels_tags"):
        values = product.get(key)
        if isinstance(values, list):
            for v in values:
                s = str(v).strip()
                if not s:
                    continue
                if ":" in s:
                    s = s.split(":", 1)[1]
                if s.lower() not in {t.lower() for t in tags}:
                    tags.append(s)
    if tags:
        result["tags"] = tags

    # Ingredients
    ingredients: List[str] = []
    ing_list = product.get("ingredients")
    if isinstance(ing_list, list):
        for obj in ing_list:
            text = obj.get("text") if isinstance(obj, dict) else str(obj)
            if not text:
                continue
            t = str(text).strip()
            if t and t.lower() not in {i.lower() for i in ingredients}:
                ingredients.append(t)
    else:
        text = product.get("ingredients_text")
        if isinstance(text, str):
            for part in text.split(","):
                t = part.strip()
                if t and t.lower() not in {i.lower() for i in ingredients}:
                    ingredients.append(t)
    if ingredients:
        result["ingredients"] = ingredients

    # Nutrition facts (per 100g)
    nutriments = product.get("nutriments") or {}
    nutrition: Dict[str, float] = {}
    mapping = {
        "energy-kcal_100g": "calories",
        "proteins_100g": "protein",
        "fat_100g": "fat",
        "carbohydrates_100g": "carbs",
        "fiber_100g": "fiber",
        "sugars_100g": "sugars",
    }
    for src, dst in mapping.items():
        value = nutriments.get(src)
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if num:
            nutrition[dst] = num
    if nutrition:
        result["nutrition"] = nutrition

    return result or None
