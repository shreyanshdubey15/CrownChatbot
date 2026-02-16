"""
Restricted Items Store — Append-only versioned store for items that are
NOT provided, illegal, or scam/fraud.

Categories:
  - not_provided : Services/products the company does not offer
  - illegal      : Activities that are illegal
  - scam_fraud   : Known scam / fraud patterns

Each item has provenance (who added it, when, optional source doc).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STORE_PATH = os.path.join(DATA_DIR, "restricted_items.json")

VALID_CATEGORIES = {"not_provided", "illegal", "scam_fraud"}


def _load() -> Dict:
    """Load the store from disk."""
    if os.path.exists(STORE_PATH):
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"items": [], "version": 1}


def _save(store: Dict):
    """Persist the store to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def get_all_items(category: Optional[str] = None) -> List[Dict]:
    """Return all restricted items, optionally filtered by category."""
    store = _load()
    items = [i for i in store["items"] if not i.get("deleted")]
    if category and category in VALID_CATEGORIES:
        items = [i for i in items if i["category"] == category]
    return items


def add_item(
    title: str,
    category: str,
    description: str = "",
    added_by: str = "admin",
    source_document: Optional[str] = None,
) -> Dict:
    """Add a new restricted item."""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}")

    store = _load()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "category": category,
        "description": description.strip(),
        "added_by": added_by,
        "source_document": source_document,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deleted": False,
    }
    store["items"].append(item)
    store["version"] += 1
    _save(store)
    return item


def update_item(
    item_id: str,
    title: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Dict]:
    """Update an existing item. Returns the updated item or None."""
    if category and category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}")

    store = _load()
    for item in store["items"]:
        if item["id"] == item_id and not item.get("deleted"):
            if title is not None:
                item["title"] = title.strip()
            if category is not None:
                item["category"] = category
            if description is not None:
                item["description"] = description.strip()
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            store["version"] += 1
            _save(store)
            return item
    return None


def delete_item(item_id: str) -> bool:
    """Soft-delete an item (append-only — never overwrite)."""
    store = _load()
    for item in store["items"]:
        if item["id"] == item_id and not item.get("deleted"):
            item["deleted"] = True
            item["deleted_at"] = datetime.now(timezone.utc).isoformat()
            store["version"] += 1
            _save(store)
            return True
    return False


def get_counts() -> Dict[str, int]:
    """Return count per category."""
    items = get_all_items()
    counts = {c: 0 for c in VALID_CATEGORIES}
    counts["total"] = 0
    for item in items:
        cat = item.get("category", "not_provided")
        if cat in counts:
            counts[cat] += 1
        counts["total"] += 1
    return counts


def search_items(query: str) -> List[Dict]:
    """Simple text search across titles and descriptions."""
    query_lower = query.lower().strip()
    if not query_lower:
        return get_all_items()
    items = get_all_items()
    return [
        i for i in items
        if query_lower in i["title"].lower()
        or query_lower in i.get("description", "").lower()
    ]


