"""
Ingestion Routes — Upload & Delete
=====================================
/upload-doc, /batch-upload, /delete-all
"""

import os
import shutil
import logging
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.models import MessageResponse
from config.constants import UPLOAD_DIR, AUTOFILL_TEMP_DIR, ALL_SUPPORTED_EXTS
from rag_pipeline.loader import load_single_doc
from rag_pipeline.chunker import chunk_documents
from rag_pipeline.vector_store import WeaviateVectorStore
from rag_pipeline.file_registry import add_uploaded_file, clear_registry
from memory.document_versions import get_document_version_store, reset_document_version_store
from utils.form_filler import safe_remove

logger = logging.getLogger("ingestion.routes")
router = APIRouter(tags=["Ingestion"])


@router.post("/upload-doc", status_code=status.HTTP_201_CREATED)
async def upload_doc(file: UploadFile = File(...), request: Request = None):
    """
    Upload a document to the knowledge base.
    Supports: PDF, Word, RTF, Excel, CSV, TSV, TXT, Markdown, images.
    Features: duplicate detection, document versioning, OCR for images.
    """
    logger.info("-" * 55)
    logger.info("[UPLOAD] %s", file.filename)

    if not file.filename or not any(file.filename.lower().endswith(ext) for ext in ALL_SUPPORTED_EXTS):
        logger.warning("Unsupported format: %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supported formats: {', '.join(ALL_SUPPORTED_EXTS)}",
        )

    # 1. Save file
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("[SAVED] %s", file_path)
    except Exception as e:
        logger.error("Save failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}",
        )

    # 2. Duplicate detection & versioning
    version_store = get_document_version_store()
    file_hash = version_store.compute_hash(file_path)
    dup_check = version_store.check_duplicate(file_hash)

    if dup_check:
        safe_remove(file_path)
        return JSONResponse(
            status_code=200,
            content={
                "message": f"[WARN] Duplicate detected: {dup_check['message']}",
                "is_duplicate": True,
                "document_id": dup_check["document_id"],
            },
        )

    version_info = version_store.add_document(
        filename=file.filename,
        file_path=file_path,
        file_hash=file_hash,
    )

    # 3. Process (load → chunk → store in vector DB)
    try:
        logger.info("[LOAD] Extracting text...")
        docs = load_single_doc(file_path)

        if not docs:
            logger.warning("No text extracted from %s", file.filename)
            add_uploaded_file(file.filename)
            return JSONResponse(
                status_code=201,
                content={
                    "message": f"{file.filename} saved (no text extracted -- not indexed in search)",
                    "document_id": version_info.get("document_id"),
                    "chunks": 0,
                    "indexed": False,
                },
            )

        logger.info("[CHUNK] Chunking %d pages...", len(docs))
        chunks = chunk_documents(docs)

        if not chunks:
            logger.warning("No chunks produced (content too short)")
            add_uploaded_file(file.filename)
            return JSONResponse(
                status_code=201,
                content={
                    "message": f"{file.filename} saved (content too short for indexing)",
                    "document_id": version_info.get("document_id"),
                    "chunks": 0,
                    "indexed": False,
                },
            )

        logger.info("[STORE] Storing %d chunks in Weaviate...", len(chunks))
        store = WeaviateVectorStore(client=request.app.state.weaviate_client)
        store.store_chunks(chunks)

        add_uploaded_file(file.filename)
    except Exception as e:
        logger.error("[ERR] Processing failed: %s", e, exc_info=True)
        safe_remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )

    logger.info("[OK] %s uploaded & indexed  (doc_id=%s, v%d)",
                file.filename, version_info.get("document_id"), version_info.get("version_number", 1))
    logger.info("-" * 55)

    return JSONResponse(
        status_code=201,
        content={
            "message": f"{file.filename} uploaded and indexed successfully",
            "document_id": version_info.get("document_id"),
            "version_number": version_info.get("version_number", 1),
            "is_new": version_info.get("is_new", True),
        },
    )


@router.post("/batch-upload", summary="Upload multiple documents at once")
async def batch_upload(files: List[UploadFile] = File(...), request: Request = None):
    """Batch upload multiple documents with per-file status tracking."""
    results = []

    for file in files:
        file_result = {
            "filename": file.filename,
            "status": "pending",
            "message": "",
            "document_id": None,
        }

        if not file.filename or not any(file.filename.lower().endswith(ext) for ext in ALL_SUPPORTED_EXTS):
            file_result["status"] = "error"
            file_result["message"] = f"Unsupported format. Supported: {', '.join(ALL_SUPPORTED_EXTS)}"
            results.append(file_result)
            continue

        file_path = os.path.join(UPLOAD_DIR, file.filename)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            file_result["status"] = "error"
            file_result["message"] = f"Save failed: {str(e)}"
            results.append(file_result)
            continue

        version_store = get_document_version_store()
        file_hash = version_store.compute_hash(file_path)
        dup_check = version_store.check_duplicate(file_hash)

        if dup_check:
            safe_remove(file_path)
            file_result["status"] = "duplicate"
            file_result["message"] = dup_check["message"]
            file_result["document_id"] = dup_check["document_id"]
            results.append(file_result)
            continue

        version_info = version_store.add_document(
            filename=file.filename,
            file_path=file_path,
            file_hash=file_hash,
        )

        try:
            docs = load_single_doc(file_path)

            if not docs:
                add_uploaded_file(file.filename)
                file_result["status"] = "success"
                file_result["message"] = "Saved (no text extracted -- not indexed)"
                file_result["document_id"] = version_info.get("document_id")
                results.append(file_result)
                continue

            chunks = chunk_documents(docs)
            if not chunks:
                add_uploaded_file(file.filename)
                file_result["status"] = "success"
                file_result["message"] = "Saved (content too short for indexing)"
                file_result["document_id"] = version_info.get("document_id")
                results.append(file_result)
                continue

            store = WeaviateVectorStore(client=request.app.state.weaviate_client)
            store.store_chunks(chunks)
            add_uploaded_file(file.filename)

            file_result["status"] = "success"
            file_result["message"] = f"Uploaded and indexed ({len(chunks)} chunks)"
            file_result["document_id"] = version_info.get("document_id")

        except Exception as e:
            safe_remove(file_path)
            file_result["status"] = "error"
            file_result["message"] = f"Processing failed: {str(e)}"

        results.append(file_result)

    total = len(results)
    success = sum(1 for r in results if r["status"] == "success")
    duplicates = sum(1 for r in results if r["status"] == "duplicate")
    errors = sum(1 for r in results if r["status"] == "error")

    return {
        "total": total,
        "success": success,
        "duplicates": duplicates,
        "errors": errors,
        "results": results,
    }


@router.delete("/delete-all", response_model=MessageResponse)
def delete_all_data(request: Request):
    """Wipe ALL data: vector store, file registry, uploads, version store, memory, autofill temp."""
    try:
        store = WeaviateVectorStore(client=request.app.state.weaviate_client)
        store.delete_all()

        clear_registry()

        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                fp = os.path.join(UPLOAD_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)

        reset_document_version_store()

        mem_path = os.path.join("data", "structured_memory.json")
        if os.path.exists(mem_path):
            with open(mem_path, "w", encoding="utf-8") as fh:
                fh.write("{}")

        if os.path.exists(AUTOFILL_TEMP_DIR):
            for f in os.listdir(AUTOFILL_TEMP_DIR):
                fp = os.path.join(AUTOFILL_TEMP_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)

        return MessageResponse(message="All data has been cleared successfully.")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wipe failed: {str(e)}",
        )


