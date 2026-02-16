"""
Restricted Items Routes
========================
/restricted-items CRUD + file extraction
"""

import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException

from api.models import RestrictedItemCreate, RestrictedItemUpdate
from config.constants import ALL_SUPPORTED_EXTS
from rag_pipeline.loader import load_single_doc
from memory.restricted_items_store import (
    get_all_items as get_restricted_items,
    add_item as add_restricted_item,
    update_item as update_restricted_item,
    delete_item as delete_restricted_item,
    get_counts as get_restricted_counts,
    search_items as search_restricted_items,
)
from utils.form_filler import cleanup_temp

router = APIRouter(tags=["Restricted Items"])


@router.get("/restricted-items", summary="List all restricted items")
def list_restricted_items(category: Optional[str] = None):
    """Get all restricted items (not provided / illegal / scam-fraud)."""
    try:
        items = get_restricted_items(category=category)
        counts = get_restricted_counts()
        return {"items": items, "counts": counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: /search must be defined BEFORE /{item_id} to avoid routing conflicts
@router.get("/restricted-items/search", summary="Search restricted items")
def search_restricted(q: str = ""):
    """Search restricted items by title or description."""
    items = search_restricted_items(q)
    return {"items": items, "count": len(items)}


@router.post("/restricted-items", summary="Add a restricted item", status_code=201)
def create_restricted_item(req: RestrictedItemCreate):
    """Add a new item to the restricted/blocked list."""
    try:
        item = add_restricted_item(
            title=req.title,
            category=req.category,
            description=req.description,
            added_by=req.added_by,
            source_document=req.source_document,
        )
        return {"message": "Item added", "item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/restricted-items/{item_id}", summary="Update a restricted item")
def edit_restricted_item(item_id: str, req: RestrictedItemUpdate):
    """Update an existing restricted item."""
    try:
        item = update_restricted_item(
            item_id=item_id,
            title=req.title,
            category=req.category,
            description=req.description,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"message": "Item updated", "item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/restricted-items/{item_id}", summary="Delete a restricted item")
def remove_restricted_item(item_id: str):
    """Soft-delete a restricted item."""
    ok = delete_restricted_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted"}


@router.post("/restricted-items/extract-from-file", summary="Upload a file and extract restricted items using LLM")
async def extract_restricted_from_file(file: UploadFile = File(...)):
    """
    Upload a document containing restricted items.
    The LLM extracts and categorizes each item for user review.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALL_SUPPORTED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Supported: {', '.join(ALL_SUPPORTED_EXTS)}",
        )

    tmp_dir = tempfile.mkdtemp(prefix="ri_extract_")
    tmp_path = os.path.join(tmp_dir, file.filename)
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        docs = load_single_doc(tmp_path)
        if not docs:
            raise HTTPException(status_code=422, detail="Could not extract text from the file")

        full_text = "\n\n".join(d.page_content for d in docs if d.page_content.strip())
        if not full_text.strip():
            raise HTTPException(status_code=422, detail="File appears empty or unreadable")

        MAX_CHARS = 25000
        if len(full_text) > MAX_CHARS:
            full_text = full_text[:MAX_CHARS] + "\n\n[... truncated ...]"

        from rag_pipeline.llm_client import get_sync_client, get_model

        client = get_sync_client()
        model = get_model("primary")

        prompt = (
            "You are a compliance document analyst. Extract ALL restricted, blocked, "
            "not-provided, illegal, or scam/fraud items from this document.\n\n"
            "For each item, determine its category:\n"
            "  - not_provided : Service or product the company does NOT offer\n"
            "  - illegal : Activity prohibited by law\n"
            "  - scam_fraud : Known scam, fraud, or deceptive pattern\n\n"
            "Return a JSON array of objects with these fields:\n"
            "  - title: short name of the restricted item (max 80 chars)\n"
            "  - category: one of 'not_provided', 'illegal', 'scam_fraud'\n"
            "  - description: brief explanation (1-2 sentences)\n\n"
            "IMPORTANT:\n"
            "- Extract EVERY item mentioned, even if there are many\n"
            "- If the document lists things that are NOT allowed, NOT supported, "
            "blocked, restricted, or prohibited — include them ALL\n"
            "- Return ONLY the JSON array, no other text\n"
            "- If no restricted items are found, return an empty array []\n\n"
            f"DOCUMENT TEXT:\n{full_text}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()

        import json as json_mod
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            items = json_mod.loads(raw)
        except json_mod.JSONDecodeError:
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1:
                items = json_mod.loads(raw[start:end + 1])
            else:
                raise HTTPException(
                    status_code=500,
                    detail="LLM did not return valid JSON. Try again.",
                )

        valid_cats = {"not_provided", "illegal", "scam_fraud"}
        cleaned = []
        for item in items:
            if isinstance(item, dict) and "title" in item:
                cat = item.get("category", "not_provided")
                if cat not in valid_cats:
                    cat = "not_provided"
                cleaned.append({
                    "title": str(item["title"]).strip()[:120],
                    "category": cat,
                    "description": str(item.get("description", "")).strip()[:300],
                    "source_document": file.filename,
                })

        return {
            "message": f"Extracted {len(cleaned)} items from {file.filename}",
            "filename": file.filename,
            "items": cleaned,
            "text_length": len(full_text),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
    finally:
        cleanup_temp(tmp_dir)


