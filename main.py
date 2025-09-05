from datetime import datetime, date
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, Field, constr
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="BananaFuel", version="1.0.0")

# ---- Mongo setup ----
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://mongo:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.bananafuel

# ---- Auth ----
async def require_key(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")

# ---- Pydantic models ----
class Serving(BaseModel):
    amount: float = Field(gt=0)
    unit: constr(strip_whitespace=True, to_lower=True)  # e.g., "g"

class Macros(BaseModel):
    energy_kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    sugar_g: float = Field(ge=0)
    fiber_g: float = Field(ge=0)

class FoodCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    serving: Serving
    macros_per_serving: Macros
    tags: List[str] = []
    source: Optional[str] = "user"

class FoodOut(FoodCreate):
    id: str
    created_at: str
    updated_at: str

def oid_str(oid): return str(oid)

async def food_doc_to_out(doc) -> FoodOut:
    return FoodOut(
        id=oid_str(doc["_id"]),
        name=doc["name"],
        brand=doc.get("brand"),
        serving=doc["serving"],
        macros_per_serving=doc["macros_per_serving"],
        tags=doc.get("tags", []),
        source=doc.get("source", "user"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )

@app.post("/foods", response_model=FoodOut, dependencies=[Depends(require_key)])
async def create_food(payload: FoodCreate):
    now = datetime.utcnow().isoformat()
    doc = payload.model_dump()
    doc.update({"created_at": now, "updated_at": now})
    res = await db.foods.insert_one(doc)
    created = await db.foods.find_one({"_id": res.inserted_id})
    return await food_doc_to_out(created)

@app.get("/foods/{food_id}", response_model=FoodOut, dependencies=[Depends(require_key)])
async def get_food(food_id: str):
    try:
        _id = ObjectId(food_id)
    except Exception:
        raise HTTPException(404, "Invalid id")
    doc = await db.foods.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Not found")
    return await food_doc_to_out(doc)

@app.get("/foods/search", response_model=List[FoodOut], dependencies=[Depends(require_key)])
async def search_foods(q: str, limit: int = 20):
    # simple case-insensitive search on name/brand/tags
    cursor = db.foods.find({
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}}
        ]
    }).limit(min(limit, 50))
    results = []
    async for doc in cursor:
        results.append(await food_doc_to_out(doc))
    return results

# ---- Entries ----
class Amount(BaseModel):
    value: float = Field(gt=0)
    unit: constr(strip_whitespace=True, to_lower=True) = "g"

class EntryCreate(BaseModel):
    user_id: str = "suki"
    food_id: str
    datetime: Optional[str] = None
    amount: Amount
    note: Optional[str] = None

class EntryOut(BaseModel):
    id: str
    user_id: str
    food_id: str
    datetime: str
    amount: Amount
    note: Optional[str]
    derived_totals: Macros

def scale_macros(m: dict, factor: float) -> dict:
    return {k: round(m[k] * factor, 3) for k in m}

@app.post("/entries", response_model=EntryOut, dependencies=[Depends(require_key)])
async def create_entry(payload: EntryCreate):
    # fetch food
    try:
        _fid = ObjectId(payload.food_id)
    except Exception:
        raise HTTPException(400, "Invalid food_id")
    food = await db.foods.find_one({"_id": _fid})
    if not food:
        raise HTTPException(404, "Food not found")

    # compute factor by mass only (g); extend later for ml/portion
    if payload.amount.unit != "g" or food["serving"]["unit"] != "g":
        raise HTTPException(400, "Currently only 'g' supported for amount and serving.")
    factor = payload.amount.value / food["serving"]["amount"]
    derived = scale_macros(food["macros_per_serving"], factor)

    dt = payload.datetime or datetime.utcnow().isoformat()
    doc = {
        "user_id": payload.user_id,
        "food_id": _fid,
        "datetime": dt,
        "amount": payload.amount.model_dump(),
        "note": payload.note,
        "derived_totals": derived
    }
    res = await db.entries.insert_one(doc)
    return EntryOut(
        id=oid_str(res.inserted_id),
        user_id=doc["user_id"],
        food_id=str(_fid),
        datetime=dt,
        amount=payload.amount,
        note=payload.note,
        derived_totals=derived
    )

@app.get("/entries", response_model=List[EntryOut], dependencies=[Depends(require_key)])
async def list_entries(user_id: str, frm: Optional[str] = None, to: Optional[str] = None, limit: int = 200):
    query = {"user_id": user_id}
    if frm or to:
        rng = {}
        if frm: rng["$gte"] = frm
        if to: rng["$lte"] = to
        query["datetime"] = rng
    cur = db.entries.find(query).sort("datetime", -1).limit(min(limit, 500))
    out = []
    async for e in cur:
        out.append(EntryOut(
            id=oid_str(e["_id"]),
            user_id=e["user_id"],
            food_id=str(e["food_id"]),
            datetime=e["datetime"],
            amount=e["amount"],
            note=e.get("note"),
            derived_totals=e["derived_totals"]
        ))
    return out

@app.get("/summary/daily", dependencies=[Depends(require_key)])
async def summary_daily(user_id: str, date_str: str):
    # aggregate totals for date (UTC)
    start = f"{date_str}T00:00:00Z"
    end   = f"{date_str}T23:59:59Z"
    pipeline = [
        {"$match": {"user_id": user_id, "datetime": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": None,
            "energy_kcal": {"$sum": "$derived_totals.energy_kcal"},
            "protein_g":   {"$sum": "$derived_totals.protein_g"},
            "fat_g":       {"$sum": "$derived_totals.fat_g"},
            "carbs_g":     {"$sum": "$derived_totals.carbs_g"},
            "sugar_g":     {"$sum": "$derived_totals.sugar_g"},
            "fiber_g":     {"$sum": "$derived_totals.fiber_g"},
        }}
    ]
    agg = await db.entries.aggregate(pipeline).to_list(1)
    totals = agg[0] if agg else {"energy_kcal": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0, "sugar_g": 0, "fiber_g": 0}
    # fetch latest goal
    goal = await db.goals.find_one({"user_id": user_id}, sort=[("effective_from", -1)])
    return {"date": date_str, "totals": totals, "goal": goal and goal.get("daily")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
