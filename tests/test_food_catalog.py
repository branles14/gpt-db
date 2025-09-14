import os
from typing import Any, Dict

from bson import ObjectId
from fastapi.testclient import TestClient

from gpt_db.app import create_app
import gpt_db.api.food.catalog as catalog
import gpt_db.db.mongo as mongo


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list[Dict[str, Any]] = []

    async def find_one(self, query: Dict[str, Any]) -> Dict[str, Any] | None:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc.copy()
        return None

    async def insert_one(self, doc: Dict[str, Any]):
        stored = doc.copy()
        stored["_id"] = ObjectId()
        self.docs.append(stored)

        class Result:
            acknowledged = True
            inserted_id = stored["_id"]

        return Result()

    def find(self, query: Dict[str, Any] | None):
        async def generator():
            for doc in self.docs:
                yield doc.copy()

        return generator()


class FakeDB:
    def __init__(self) -> None:
        self.collections = {"catalog": FakeCollection()}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections[name]


class FakeMongoClient:
    def __init__(self) -> None:
        self.db = FakeDB()

    def get_database(self, name: str) -> FakeDB:
        return self.db


def create_client(monkeypatch) -> TestClient:
    os.environ.setdefault("API_KEY", "secret")
    os.environ.setdefault("MONGO_URI", "mongodb://example.com")
    fake_client = FakeMongoClient()
    monkeypatch.setattr(catalog, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(mongo, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(mongo, "ensure_indexes", lambda: None)
    app = create_app()
    return TestClient(app)


def test_unknown_nutrition_key_returns_422(monkeypatch):
    payload = {"name": "Mystery", "nutrition": {"calories": 10, "bogus": 1}}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 422


def test_empty_nutrition_object_returns_422(monkeypatch):
    payload = {"name": "Empty", "nutrition": {}}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 422


def test_full_nutrition_persists(monkeypatch):
    nutrition = {
        "calories": 100,
        "protein": 5,
        "fat": 1,
        "carbs": 20,
        "fiber": 3,
        "sugars": 10,
        "saturated_fat": 0.5,
        "trans_fat": 0.0,
        "cholesterol_mg": 1,
        "sodium_mg": 2,
        "potassium_mg": 3,
        "calcium_mg": 4,
        "iron_mg": 5,
        "magnesium_mg": 6,
        "phosphorus_mg": 7,
        "zinc_mg": 8,
        "selenium_mcg": 9,
        "copper_mg": 10,
        "manganese_mg": 11,
        "vitamin_a_mcg": 12,
        "vitamin_c_mg": 13,
        "vitamin_d_mcg": 14,
        "vitamin_e_mg": 15,
        "vitamin_k_mcg": 16,
        "thiamin_mg": 17,
        "riboflavin_mg": 18,
        "niacin_mg": 19,
        "vitamin_b6_mg": 20,
        "folate_mcg": 21,
        "vitamin_b12_mcg": 22,
    }
    payload = {"name": "Complete", "nutrition": nutrition}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201

        list_resp = client.get("/food/catalog", headers={"x-api-key": "secret"})
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert any(
            item["name"] == "Complete" and item["nutrition"] == nutrition for item in items
        )

