import os
from typing import Any, Dict, Iterable

from bson import ObjectId
from fastapi.testclient import TestClient

from gpt_db.app import create_app
import gpt_db.api.catalog as catalog
import gpt_db.api.log as log
import gpt_db.api.stock as stock
import gpt_db.api.targets as targets
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

    async def update_one(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        doc = await self.find_one(filter)
        created = False
        if doc is None and upsert:
            doc = {**filter, "_id": ObjectId()}
            self.docs.append(doc)
            created = True
        if doc is None:
            class Result:
                acknowledged = True
                upserted_id = None
            return Result()
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        if "$set" in update:
            doc.update(update["$set"])
        if "$setOnInsert" in update and created:
            doc.update(update["$setOnInsert"])

        class Result:
            acknowledged = True
            upserted_id = doc["_id"] if created else None

        return Result()

    def find(self, query: Dict[str, Any] | None = None):
        async def generator():
            for doc in self.docs:
                if not query or all(doc.get(k) == v for k, v in query.items()):
                    yield doc.copy()
        return generator()


class FakeDB:
    def __init__(self, collections: Iterable[str] = ("catalog", "stock")) -> None:
        self.collections = {name: FakeCollection() for name in collections}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections[name]


class FakeMongoClient:
    def __init__(self, collections: Iterable[str] = ("catalog", "stock")) -> None:
        self.db = FakeDB(collections)

    def get_database(self, name: str) -> FakeDB:
        return self.db


def create_client(monkeypatch, collections: Iterable[str] = ("catalog", "stock")) -> TestClient:
    os.environ.setdefault("API_KEY", "secret")
    os.environ.setdefault("MONGO_URI", "mongodb://example.com")
    fake_client = FakeMongoClient(collections)
    monkeypatch.setattr(mongo, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(mongo, "ensure_indexes", lambda: None)
    monkeypatch.setattr(catalog, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(stock, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(log, "get_mongo_client", lambda: fake_client)
    monkeypatch.setattr(targets, "get_mongo_client", lambda: fake_client)
    app = create_app()
    return TestClient(app)
