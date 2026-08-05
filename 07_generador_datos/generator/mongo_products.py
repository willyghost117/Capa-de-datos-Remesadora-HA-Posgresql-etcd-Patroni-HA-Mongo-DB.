from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: Path, documents: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(documents, fh, ensure_ascii=False, indent=2, default=json_default)


def load_mongo(uri: str, database: str, products: dict[str, list[dict[str, Any]]]) -> tuple[bool, str]:
    try:
        from pymongo import MongoClient, ReplaceOne
    except ImportError:
        return False, "pymongo is not installed; JSON files were generated instead."

    client = MongoClient(uri)
    db = client[database]
    for collection_name, docs in products.items():
        if not docs:
            continue
        collection = db[collection_name]
        if collection_name in {"remittance_events", "fraud_signals", "fx_rate_timeseries"}:
            collection.insert_many(docs, ordered=False)
            continue
        operations = []
        for doc in docs:
            operations.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if operations:
            collection.bulk_write(operations, ordered=False)
    client.close()
    return True, "MongoDB products loaded successfully."
