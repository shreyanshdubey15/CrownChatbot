"""
Autofill Routes
================
/autofill-form, /build-profile, /download-autofill-report,
/autofill-compare, /batch-autofill
"""

import os
import uuid
import shutil
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
    """
    value_map: Dict[str, str] = {}
    for f in fields:
        val = f.get("value")
        conf = f.get("confidence", 0)
        # STRICT: Only fill form with 100% confidence data
        if not val or conf < 1.0:
            continue
        # Primary key: detected field name
        field_name = f.get("field", "")
        if field_name:
            value_map[field_name] = val
        # Canonical key + all aliases
        canonical = f.get("canonical")
        if canonical:
            # Add the canonical key itself (underscored)
            value_map[canonical] = val
            # Add readable canonical (spaces instead of underscores)
            value_map[canonical.replace("_", " ")] = val
            # Add ALL aliases from the dictionary
            if canonical in FIELD_ALIASES:
                for alias in FIELD_ALIASES[canonical]:
                    if alias not in value_map:  # Don't overwrite earlier entries
                        value_map[alias] = val
    return value_map


@router.post("/autofill-form", response_model=AutofillResponse, summary="Autofill a form using the knowledge base")
async def autofill_form(
    request: Request,
    file: UploadFile = File(..., description="The form to autofill"),
    company_id: Optional[str] = Form(None, description="Company ID for scoped retrieval"),
):
    """Upload a form → Detect fields → Retrieve data → Autofill → Fill original form."""
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    try:
        docs = load_single_doc(saved_path)
        if not docs:
            raise ValueError("Could not extract text from the uploaded form.")
        form_text = "\n\n".join(d.page_content for d in docs)
    except Exception as exc:
        safe_remove(saved_path)
        raise HTTPException(status_code=500, detail=f"Form text extraction failed: {exc}")

    try:
        engine: AutofillEngine = request.app.state.autofill_engine
        result = await engine.autofill_form_async(
            form_text=form_text,
            document_name=file.filename,
            company_id=company_id,
        )
    except Exception as exc:
        safe_remove(saved_path)
        raise HTTPException(status_code=500, detail=f"Autofill engine error: {exc}")

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
    except Exception as exc:
        print(f"[FILL WARNING] Could not fill form programmatically: {exc}")
        shutil.copy2(saved_path, filled_path)

    meta = result.get("metadata", {})
    meta["file_id"] = file_id
    meta["file_ext"] = ext
    result["metadata"] = meta

    return result


@router.post("/build-profile", response_model=BuildProfileResponse, summary="Build a Master Company Profile")
async def build_profile(body: BuildProfileRequest, request: Request):
    """Entity Builder — creates a structured company profile from ALL documents."""
    try:
        engine: AutofillEngine = request.app.state.autofill_engine
        result = await engine.build_company_profile_async(body.company_id)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Profile build failed: {exc}")


@router.post("/download-autofill-report", summary="Download the filled form in the SAME format as uploaded")
def download_autofill_report(body: DownloadAutofillRequest):
    """Returns the programmatically filled document."""
    file_id  = body.metadata.file_id  if body.metadata else None
    file_ext = body.metadata.file_ext if body.metadata else None

    if not file_id or not file_ext:
        raise HTTPException(status_code=400, detail="Missing file_id/file_ext in metadata. Re-run autofill.")

    filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_filled.{file_ext}")
    if not os.path.exists(filled_path):
        raise HTTPException(status_code=404, detail="Filled form not found. Please re-run autofill.")

    safe_name = body.document.rsplit(".", 1)[0] if "." in body.document else body.document
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name).strip()
    filename = f"{safe_name}_Autofilled.{file_ext}"

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

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if not any(f".{ext}" == e for e in ALL_SUPPORTED_EXTS):
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    try:
        fields = _json.loads(fields_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid fields_json.")

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}.{ext}")

    try:
        with open(saved_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    # Build expanded value map from user-edited fields
    value_map = _build_expanded_value_map(fields)

    filled_path = os.path.join(AUTOFILL_TEMP_DIR, f"{file_id}_refilled.{ext}")
    try:
        if ext == "pdf":
            fill_pdf_form(saved_path, filled_path, value_map)
        elif ext in ("docx", "doc"):
            fill_docx_form(saved_path, filled_path, value_map)
        else:
            shutil.copy2(saved_path, filled_path)
    except Exception as exc:
        print(f"[REFILL WARNING] Could not fill form: {exc}")
        shutil.copy2(saved_path, filled_path)

    safe_name = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name).strip()
    filename = f"{safe_name}_Autofilled.{ext}"

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


