"""
Document Ingestion API v2
==========================
Full pipeline: upload → classify → extract (layout-aware) →
  build entity → store vectors → update graph → audit log.

Every document upload triggers the autonomous profile builder.
"""

import os
import uuid
import hashlib
import shutil
import time
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from config.settings import settings
from core.schemas.enums import DocumentType, AuditAction
from core.schemas.document import DocumentMeta


router = APIRouter(prefix="/v2/ingest", tags=["Ingestion v2"])


# ── Response Models ──────────────────────────────────────────

class IngestResponse(BaseModel):
    document_id: str
    filename: str
    document_type: str
    classification_confidence: float
    fields_extracted: int
    fields_filled: int
    company_id: Optional[str] = None
    processing_duration_ms: int
    warnings: List[str] = []


class BatchIngestResponse(BaseModel):
    total_documents: int
    successful: int
    failed: int
    results: List[IngestResponse]


# ── Endpoints ────────────────────────────────────────────────

@router.post(
    "/document",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a document into the intelligence platform",
)
async def ingest_document(
    request: Request,
    file: UploadFile = File(..., description="Document to ingest (.pdf, .docx, .doc)"),
    company_id: Optional[str] = Form(None, description="Company ID for entity linking"),
):
    """
    Full document ingestion pipeline:

    1. Validate + save file
    2. Classify document type (AI)
    3. Extract text (layout-aware for scanned PDFs)
    4. Chunk + embed + store in vector DB
    5. Extract structured fields via dual-LLM pipeline
    6. Build/update company entity profile
    7. Update entity graph
    8. Write audit trail

    Returns extraction summary with field counts.
    """
    start_time = time.time()
    warnings: List[str] = []

    # ── Step 1: Validate ─────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(status_code=400, detail="Only .pdf, .docx, .doc supported.")

    # Generate document ID and save
    document_id = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{document_id}.{ext}")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    try:
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    # Compute file hash for dedup
    file_hash = _compute_file_hash(file_path)

    # ── Step 2: Classify ─────────────────────────────────────
    try:
        from ingestion.classifier import get_classifier
        from rag_pipeline.loader import load_single_doc

        # Extract text first (needed for content-based classification)
        docs = load_single_doc(file_path)
        if not docs:
            _safe_remove(file_path)
            raise HTTPException(status_code=500, detail="Document extraction failed — all tiers failed.")

        full_text = "\n\n".join(d.page_content for d in docs)

        classifier = get_classifier()
        doc_type, class_confidence = classifier.classify(file.filename, full_text)

    except HTTPException:
        raise
    except Exception as e:
        warnings.append(f"Classification failed: {e}")
        doc_type = DocumentType.UNKNOWN
        class_confidence = 0.0
        full_text = ""
        docs = []

    # ── Step 3: Chunk + Store Vectors ────────────────────────
    fields_extracted = 0
    fields_filled = 0

    try:
        from rag_pipeline.chunker import chunk_documents

        chunks = chunk_documents(docs)

        # Use hybrid retriever for storage (enhanced metadata)
        from retrieval.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(request.app.state.weaviate_client)
        stored = retriever.store_chunks(
            chunks=chunks,
            document_id=document_id,
            document_type=doc_type.value,
            company_id=company_id or "",
        )

    except Exception as e:
        warnings.append(f"Vector storage failed: {e}")

    # ── Step 4: Structured Extraction ────────────────────────
    try:
        from extraction.schema_extractor import SchemaExtractor
        from extraction.dual_llm_validator import get_dual_validator

        validator = get_dual_validator()
        extractor = SchemaExtractor(dual_validator=validator)

        # Get memory values if company_id provided
        memory_values = {}
        if company_id:
            try:
                from entity.graph_engine import get_graph_engine
                graph = get_graph_engine()
                profile = graph.get_company(company_id)
                if profile:
                    memory_values = profile.to_flat_dict()
            except Exception:
                pass

        extraction_result = await extractor.extract(
            text=full_text,
            document_type=doc_type.value,
            document_id=document_id,
            source_document=file.filename,
            company_id=company_id,
            memory_values=memory_values,
        )

        fields_extracted = extraction_result.total_fields
        fields_filled = extraction_result.filled_fields

    except Exception as e:
        warnings.append(f"Structured extraction failed: {e}")

    # ── Step 5: Build/Update Entity Profile ──────────────────
    if company_id and fields_filled > 0:
        try:
            from entity.graph_engine import get_graph_engine
            from entity.profile_builder import ProfileBuilder
            from memory.versioned_store import get_versioned_store

            graph = get_graph_engine()
            memory = get_versioned_store()
            builder = ProfileBuilder(graph_engine=graph, versioned_memory=memory)

            builder.build_or_update_profile(
                company_id=company_id,
                extracted_fields=extraction_result.fields,
                document_id=document_id,
                document_type=doc_type.value,
                filename=file.filename,
            )

        except Exception as e:
            warnings.append(f"Profile build failed: {e}")

    # ── Step 6: Audit Trail ──────────────────────────────────
    try:
        from memory.versioned_store import get_audit_writer

        audit = get_audit_writer()
        audit.log(
            action=AuditAction.DOCUMENT_UPLOADED,
            entity_type="document",
            entity_id=document_id,
            details={
                "filename": file.filename,
                "document_type": doc_type.value,
                "classification_confidence": class_confidence,
                "fields_extracted": fields_extracted,
                "fields_filled": fields_filled,
                "company_id": company_id,
                "file_hash": file_hash,
            },
        )
    except Exception:
        pass  # Audit failure should never block ingestion

    duration_ms = int((time.time() - start_time) * 1000)

    return IngestResponse(
        document_id=document_id,
        filename=file.filename,
        document_type=doc_type.value,
        classification_confidence=class_confidence,
        fields_extracted=fields_extracted,
        fields_filled=fields_filled,
        company_id=company_id,
        processing_duration_ms=duration_ms,
        warnings=warnings,
    )


# ── Helpers ──────────────────────────────────────────────────

def _compute_file_hash(filepath: str) -> str:
    """SHA-256 hash for deduplication."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass






