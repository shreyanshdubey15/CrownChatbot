"""
Autofill Routes
================
/autofill-form, /build-profile, /download-autofill-report,
/autofill-compare, /batch-autofill
"""

import os
import uuid
import shutil
import logging
from typing import Optional, List, Dict

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.models import (
    AutofillResponse, BuildProfileRequest, BuildProfileResponse,
    DownloadAutofillRequest,
)
from config.constants import AUTOFILL_TEMP_DIR, ALL_SUPPORTED_EXTS
from rag_pipeline.loader import load_single_doc
from rag_pipeline.autofill_engine import AutofillEngine, FIELD_ALIASES
from utils.form_filler import fill_pdf_form, fill_docx_form, safe_remove

logger = logging.getLogger("autofill.routes")
router = APIRouter(tags=["Autofill"])


def _build_expanded_value_map(fields: list) -> Dict[str, str]:
    """
    Build an expanded value map for physical form filling.

    For each filled field, creates entries keyed by:
      1. The detected field name  (e.g. "Company Name")
      2. The canonical key        (e.g. "company_name")
      3. ALL aliases for that canonical key (e.g. "business name", "legal name", ...)

    This dramatically improves matching against PDF widget names
    and DOCX cell labels that may use different phrasing.

    When multiple fields share the same canonical key, the BEST
    value is selected — for name-type fields text values are preferred
    over pure numbers.  The chosen canonical value is applied back to
    the field list IN-PLACE so that the frontend also displays the
    consistent correct value (not just the form-filler).
    """

    # --- Canonical keys that should NEVER be pure numbers ---
    _NAME_CANONICALS = {
        "company_name", "authorized_representative", "contact_name",
        "billing_contact", "technical_contact", "compliance_contact",
        "entity_type", "state_of_incorporation", "country",
        "address", "billing_address", "city", "state",
    }

    # ── Pass 1: collect ALL candidate values per canonical ──
    canonical_candidates: Dict[str, list] = {}
    for f in fields:
        val = f.get("value")
        conf = f.get("confidence", 0)
        if not val or conf < 1.0:
            continue
        canonical = f.get("canonical")
        if canonical:
            canonical_candidates.setdefault(canonical, []).append(val)

    # ── Choose best canonical value ──
    canonical_values: Dict[str, str] = {}
    for canonical, values in canonical_candidates.items():
        if canonical in _NAME_CANONICALS:
            # Prefer non-numeric values for name-type fields
            text_values = [
                v for v in values
                if not v.strip().replace("-", "").replace(" ", "").isdigit()
            ]
            if text_values:
                canonical_values[canonical] = text_values[0]
            else:
                canonical_values[canonical] = values[0]
        else:
            canonical_values[canonical] = values[0]

    # ── Pass 2: build value_map AND fix field values in-place ──
    value_map: Dict[str, str] = {}
    for f in fields:
        val = f.get("value")
        conf = f.get("confidence", 0)
        if not val or conf < 1.0:
            continue

        canonical = f.get("canonical")
        effective_val = canonical_values.get(canonical, val) if canonical else val

        # Update the field's own value for frontend consistency
        if f["value"] != effective_val:
            logger.info(
                "[FIXUP] '%s': '%s' -> '%s' (canonical consistency)",
                f.get("field", "?"),
                str(f["value"])[:50],
                str(effective_val)[:50],
            )
            f["value"] = effective_val

        # Primary key: detected field name
        field_name = f.get("field", "")
        if field_name:
            value_map[field_name] = effective_val
        # Canonical key + all aliases
        if canonical:
            value_map[canonical] = effective_val
            value_map[canonical.replace("_", " ")] = effective_val
            if canonical in FIELD_ALIASES:
                for alias in FIELD_ALIASES[canonical]:
                    if alias not in value_map:
                        value_map[alias] = effective_val
    return value_map


@router.post("/autofill-form", response_model=AutofillResponse, summary="Autofill a form using the knowledge base")
async def autofill_form(
    request: Request,
    file: UploadFile = File(..., description="The form to autofill"),
    company_id: Optional[str] = Form(None, description="Company ID for scoped retrieval"),
):
    """Upload a form → Detect fields → Retrieve data → Autofill → Fill original form."""
    logger.info("-" * 55)
    logger.info("[AUTOFILL] REQUEST: file=%s  company=%s", file.filename, company_id or "(none)")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if not any(f".{ext}" == e for e in ALL_SUPPORTED_EXTS):
        logger.warning("Unsupported format: .%s", ext)
        raise HTTPException(status_code=400, detail=f"Supported formats: {', '.join(ALL_SUPPORTED_EXTS)}")

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}.{ext}")
    try:
        with open(saved_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        logger.info("[SAVED] File -> %s", saved_path)
    except Exception as exc:
        logger.error("Failed to save file: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    try:
        logger.info("[TEXT] Extracting text from form...")
        docs = load_single_doc(saved_path)
        if not docs:
            raise ValueError("Could not extract text from the uploaded form.")
        form_text = "\n\n".join(d.page_content for d in docs)
        logger.info("[TEXT] Extracted %d chars from %d page(s)", len(form_text), len(docs))
    except Exception as exc:
        logger.error("Text extraction failed: %s", exc)
        safe_remove(saved_path)
        raise HTTPException(status_code=500, detail=f"Form text extraction failed: {exc}")

    try:
        logger.info("[ENGINE] Running autofill engine...")
        engine: AutofillEngine = request.app.state.autofill_engine
        result = await engine.autofill_form_async(
            form_text=form_text,
            document_name=file.filename,
            company_id=company_id,
        )
        logger.info("[ENGINE] Autofill engine done -- %d fields returned", len(result.get("fields", [])))
    except Exception as exc:
        logger.error("Autofill engine error: %s", exc, exc_info=True)
        safe_remove(saved_path)
        raise HTTPException(status_code=500, detail=f"Autofill engine error: {exc}")

    fields_for_fill = result.get("fields", [])
    value_map = _build_expanded_value_map(fields_for_fill)
    logger.info("[MAP] Value map has %d entries for form filling", len(value_map))
    for k, v in value_map.items():
        logger.debug("   value_map[%s] = %s", k, v[:80] if v else "(empty)")

    filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_filled.{ext}")
    try:
        logger.info("[FILL] Filling %s form -> %s", ext.upper(), filled_path)
        if ext == "pdf":
            fill_pdf_form(saved_path, filled_path, value_map)
        elif ext in ("docx", "doc"):
            fill_docx_form(saved_path, filled_path, value_map)
        else:
            shutil.copy2(saved_path, filled_path)
        logger.info("[OK] Form filled successfully")
    except Exception as exc:
        logger.warning("[WARN] Could not fill form programmatically: %s", exc)
        shutil.copy2(saved_path, filled_path)

    meta = result.get("metadata", {})
    meta["file_id"] = file_id
    meta["file_ext"] = ext
    result["metadata"] = meta

    filled_count = sum(1 for f in fields_for_fill if f.get("value"))
    logger.info("[RESULT] %d/%d fields filled  (file_id=%s)", filled_count, len(fields_for_fill), file_id)
    logger.info("-" * 55)

    return result


@router.post("/build-profile", response_model=BuildProfileResponse, summary="Build a Master Company Profile")
async def build_profile(body: BuildProfileRequest, request: Request):
    """Entity Builder — creates a structured company profile from ALL documents."""
    logger.info("[PROFILE] BUILD PROFILE: company=%s", body.company_id)
    try:
        engine: AutofillEngine = request.app.state.autofill_engine
        result = await engine.build_company_profile_async(body.company_id)
        logger.info("[PROFILE] Profile built for %s -- %d fields", body.company_id, len(result.get("fields", [])))
        return result
    except Exception as exc:
        logger.error("Profile build failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Profile build failed: {exc}")


@router.post("/download-autofill-report", summary="Download the filled form in the SAME format as uploaded")
def download_autofill_report(body: DownloadAutofillRequest):
    """Returns the programmatically filled document."""
    file_id  = body.metadata.file_id  if body.metadata else None
    file_ext = body.metadata.file_ext if body.metadata else None
    logger.info("[DOWNLOAD] REQUEST: doc=%s  file_id=%s  ext=%s", body.document, file_id, file_ext)

    if not file_id or not file_ext:
        logger.warning("Missing file_id/file_ext in metadata")
        raise HTTPException(status_code=400, detail="Missing file_id/file_ext in metadata. Re-run autofill.")

    filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_filled.{file_ext}")
    if not os.path.exists(filled_path):
        logger.warning("Filled form not found at %s", filled_path)
        raise HTTPException(status_code=404, detail="Filled form not found. Please re-run autofill.")

    safe_name = body.document.rsplit(".", 1)[0] if "." in body.document else body.document
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name).strip()
    filename = f"{safe_name}_Autofilled.{file_ext}"

    file_size = os.path.getsize(filled_path)
    logger.info("[DOWNLOAD] Serving %s (%d bytes) -> %s", filled_path, file_size, filename)

    mime_map = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc":  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    mime = mime_map.get(file_ext, "application/octet-stream")

    return StreamingResponse(
        open(filled_path, "rb"),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/autofill-compare", summary="Get side-by-side comparison of original vs filled form")
async def autofill_compare(
    request: Request,
    file: UploadFile = File(...),
    company_id: Optional[str] = Form(None),
):
    """Returns a comparison view: original value vs autofilled value for each field."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if not any(f".{ext}" == e for e in ALL_SUPPORTED_EXTS):
        raise HTTPException(status_code=400, detail=f"Supported formats: {', '.join(ALL_SUPPORTED_EXTS)}")

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}.{ext}")
    try:
        with open(saved_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        docs = load_single_doc(saved_path)
        if not docs:
            raise ValueError("Could not extract text from form.")
        form_text = "\n\n".join(d.page_content for d in docs)

        engine: AutofillEngine = request.app.state.autofill_engine
        result = await engine.autofill_form_async(
            form_text=form_text,
            document_name=file.filename,
            company_id=company_id,
        )

        comparison = []
        for field in result.get("fields", []):
            comparison.append({
                "field": field["field"],
                "original_value": None,
                "autofilled_value": field.get("value"),
                "confidence": field.get("confidence", 0),
                "source": field.get("source_document"),
                "status": "filled" if field.get("value") else "empty",
            })

        return {
            "document": file.filename,
            "comparison": comparison,
            "total_fields": len(comparison),
            "filled_fields": sum(1 for c in comparison if c["autofilled_value"]),
            "empty_fields": sum(1 for c in comparison if not c["autofilled_value"]),
            "file_id": file_id,
            "file_ext": ext,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")


@router.post("/refill-form", summary="Re-fill a form with user-edited field values")
async def refill_form(
    file: UploadFile = File(..., description="The original form to re-fill"),
    fields_json: str = Form(..., description="JSON array of field objects with user edits"),
):
    """
    Re-fill a form using user-corrected field values.
    Used after inline editing in the frontend.
    """
    import json as _json

    logger.info("-" * 55)
    logger.info("[REFILL] REQUEST: file=%s", file.filename)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if not any(f".{ext}" == e for e in ALL_SUPPORTED_EXTS):
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    try:
        fields = _json.loads(fields_json)
        logger.info("[REFILL] Received %d edited fields from user", len(fields))
    except Exception:
        logger.error("Invalid fields_json payload")
        raise HTTPException(status_code=400, detail="Invalid fields_json.")

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}.{ext}")

    try:
        with open(saved_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        logger.info("[SAVED] File -> %s", saved_path)
    except Exception as exc:
        logger.error("Failed to save file: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    # Build expanded value map from user-edited fields
    value_map = _build_expanded_value_map(fields)
    logger.info("[MAP] Refill value map has %d entries", len(value_map))
    for k, v in value_map.items():
        logger.debug("   refill_map[%s] = %s", k, v[:80] if v else "(empty)")

    filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_refilled.{ext}")
    try:
        logger.info("[FILL] Re-filling %s form -> %s", ext.upper(), filled_path)
        if ext == "pdf":
            fill_pdf_form(saved_path, filled_path, value_map)
        elif ext in ("docx", "doc"):
            fill_docx_form(saved_path, filled_path, value_map)
        else:
            shutil.copy2(saved_path, filled_path)
        logger.info("[OK] Refill done")
    except Exception as exc:
        logger.warning("[WARN] Could not refill form: %s", exc)
        shutil.copy2(saved_path, filled_path)

    safe_name = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name).strip()
    filename = f"{safe_name}_Autofilled.{ext}"

    logger.info("[DOWNLOAD] Serving refilled document -> %s", filename)
    logger.info("-" * 55)

    mime_map = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc":  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    return StreamingResponse(
        open(filled_path, "rb"),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/batch-autofill", summary="Autofill multiple forms at once")
async def batch_autofill(
    request: Request,
    files: List[UploadFile] = File(...),
    company_id: Optional[str] = Form(None),
):
    """Upload multiple blank forms and autofill all of them."""
    results = []

    for file in files:
        file_result = {
            "filename": file.filename,
            "status": "pending",
            "fields": [],
            "metadata": {},
        }

        ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
        if not any(f".{ext}" == e for e in ALL_SUPPORTED_EXTS):
            file_result["status"] = "error"
            file_result["metadata"]["error"] = f"Unsupported format. Supported: {', '.join(ALL_SUPPORTED_EXTS)}"
            results.append(file_result)
            continue

        file_id = str(uuid.uuid4())
        saved_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}.{ext}")

        try:
            with open(saved_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)

            docs = load_single_doc(saved_path)
            if not docs:
                raise ValueError("No content extracted")

            form_text = "\n\n".join(d.page_content for d in docs)

            engine: AutofillEngine = request.app.state.autofill_engine
            result = await engine.autofill_form_async(
                form_text=form_text,
                document_name=file.filename,
                company_id=company_id,
            )

            fields_for_fill = result.get("fields", [])
            value_map = _build_expanded_value_map(fields_for_fill)

            filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_filled.{ext}")
            try:
                if ext == "pdf":
                    fill_pdf_form(saved_path, filled_path, value_map)
                elif ext in ("docx", "doc"):
                    fill_docx_form(saved_path, filled_path, value_map)
                else:
                    shutil.copy2(saved_path, filled_path)
            except Exception:
                shutil.copy2(saved_path, filled_path)

            meta = result.get("metadata", {})
            meta["file_id"] = file_id
            meta["file_ext"] = ext

            file_result["status"] = "success"
            file_result["fields"] = result.get("fields", [])
            file_result["metadata"] = meta

        except Exception as exc:
            file_result["status"] = "error"
            file_result["metadata"]["error"] = str(exc)

        results.append(file_result)

    return {
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


