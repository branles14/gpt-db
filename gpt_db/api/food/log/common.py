from typing import Dict


DV_DEFAULTS: Dict[str, float] = {
    "calories": 2000,
    "protein": 50,
    "fat": 78,
    "carbs": 275,
}  # FDA Daily Values for adults and children ≥4 yrs


async def _get_targets(db) -> Dict[str, float]:
    """Fetch current macro targets, falling back to DV defaults."""
    col = db.get_collection("targets")
    doc = await col.find_one({"_id": "current"})
    if doc:
        doc.pop("_id", None)
        return {**DV_DEFAULTS, **doc}  # type: ignore[return-value]
    return dict(DV_DEFAULTS)

