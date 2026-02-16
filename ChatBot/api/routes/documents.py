"""
Document Routes
================
/documents, /document-preview, /document-download, /document-versions
"""

import os
import base64

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config.constants import UPLOAD_DIR, AUTOFILL_TEMP_DIR, IMAGE_EXTS, MIME_MAP
from rag_pipeline.loader import load_single_doc
from memory.document_versions import get_document_version_store

router = APIRouter(tags=["Documents"])


@router.get("/document-preview/{filename:path}", summary="Preview a document")
def preview_document(filename: str):
    """Returns document content for in-app preview."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(AUTOFILL_TEMP_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        return {
            "filename": filename,
            "type": "pdf",
            "content": content,
            "size": os.path.getsize(file_path),
        }
    elif f".{ext}" in IMAGE_EXTS:
        with open(file_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        ocr_text = ""
        try:
            docs = load_single_doc(file_path)
            ocr_text = "\n\n".join(d.page_content for d in docs) if docs else ""
        except Exception:
            pass

        return {
            "filename": filename,
            "type": "image",
            "content": img_b64,
            "mime_type": f"image/{'jpeg' if ext in ('jpg','jpeg','jfif') else ext}",
            "ocr_text": ocr_text[:50000] if ocr_text else None,
            "size": os.path.getsize(file_path),
        }
    else:
        try:
            docs = load_single_doc(file_path)
            text = "\n\n".join(d.page_content for d in docs) if docs else "(No content extracted)"
        except Exception as e:
            text = f"(Preview failed: {str(e)})"

        return {
            "filename": filename,
            "type": "text",
            "content": text[:50000],
            "size": os.path.getsize(file_path),
        }


@router.get("/document-download/{filename:path}", summary="Download a document")
def download_document(filename: str):
    """Download a raw uploaded document."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    ext = filename.rsplit(".", 1)[-1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
    return StreamingResponse(
        open(file_path, "rb"),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/documents", summary="List all uploaded documents with version info")
def list_documents():
    """List all documents in the knowledge base with versioning metadata."""
    version_store = get_document_version_store()
    versioned_docs = version_store.list_documents(limit=200)

    uploaded_files = []
    if os.path.exists(UPLOAD_DIR):
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if os.path.isfile(fpath):
                uploaded_files.append({
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                    "ext": fname.rsplit(".", 1)[-1].lower() if "." in fname else "",
                })

    return {
        "total_files": len(uploaded_files),
        "versioned_documents": versioned_docs,
        "files": uploaded_files,
    }


@router.get("/document-versions/{document_id}", summary="Get all versions of a document")
def get_document_versions(document_id: str):
    """Get full version history for a specific document."""
    version_store = get_document_version_store()
    record = version_store.get_document(document_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return record


