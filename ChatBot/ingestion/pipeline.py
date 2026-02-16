"""
Master Ingestion Pipeline — Orchestration Layer
=================================================
Coordinates the full document processing pipeline:

  Upload → Classify → Layout Extract → Table Extract →
  Chunk → Embed → Store → Schema Extract → Validate →
  Entity Build → Graph Update → Audit Log

This is the single entry point for document processing.
Each step is fault-tolerant — failures in one step don't block others.
"""

import os
import uuid
import time
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from config.settings import settings
from core.schemas.enums import DocumentType, AuditAction
from core.schemas.document import DocumentMeta
from core.schemas.extraction import FieldResult


class IngestionPipeline:
    """
    Stateless orchestrator for the document processing pipeline.
    Each method represents a pipeline stage.
    All state is passed explicitly — no hidden coupling.
    """

    def __init__(self, weaviate_client):
        self.weaviate_client = weaviate_client

    async def process_document(
        self,
        file_path: str,
        filename: str,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline execution.
        Returns a comprehensive result dict.
        """
        start_time = time.time()
        document_id = str(uuid.uuid4())
        warnings: List[str] = []
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # ── Stage 1: File Metadata ───────────────────────────
        file_hash = self._compute_hash(file_path)
        file_size = os.path.getsize(file_path)

        # ── Stage 2: Text Extraction ─────────────────────────
        docs, extract_warnings = self._extract_text(file_path)
        warnings.extend(extract_warnings)

        if not docs:
            return {
                "document_id": document_id,
                "status": "failed",
                "error": "All extraction tiers failed",
                "warnings": warnings,
                "processing_duration_ms": int((time.time() - start_time) * 1000),
            }

        full_text = "\n\n".join(d.page_content for d in docs)

        # ── Stage 3: Classification ──────────────────────────
        doc_type, class_confidence = self._classify(filename, full_text)

        # ── Stage 4: Layout Extraction (for scanned PDFs) ────
        layout_elements = []
        tables = []
        if ext == "pdf" and settings.ENABLE_LAYOUT_EXTRACTION:
            layout_elements, tables, layout_warnings = self._extract_layout(
                file_path, document_id,
            )
            warnings.extend(layout_warnings)

        # ── Stage 5: Chunking + Vector Storage ───────────────
        chunks_stored = 0
        try:
            from rag_pipeline.chunker import chunk_documents
            from retrieval.hybrid_retriever import HybridRetriever

            chunks = chunk_documents(docs)
            retriever = HybridRetriever(self.weaviate_client)
            chunks_stored = retriever.store_chunks(
                chunks=chunks,
                document_id=document_id,
                document_type=doc_type.value,
                company_id=company_id or "",
            )
        except Exception as e:
            warnings.append(f"Vector storage failed: {e}")

        # ── Stage 6: Structured Extraction ───────────────────
        extraction_result = None
        field_results: List[FieldResult] = []

        try:
            from extraction.schema_extractor import SchemaExtractor
            from extraction.dual_llm_validator import get_dual_validator

            # Get memory values
            memory_values = self._get_memory_values(company_id)

            validator = get_dual_validator()
            extractor = SchemaExtractor(dual_validator=validator)

            extraction_result = await extractor.extract(
                text=full_text,
                document_type=doc_type.value,
                document_id=document_id,
                source_document=filename,
                company_id=company_id,
                memory_values=memory_values,
            )
            field_results = extraction_result.fields

        except Exception as e:
            warnings.append(f"Structured extraction failed: {e}")

        # ── Stage 7: Entity Profile Build ────────────────────
        if company_id and field_results:
            try:
                from entity.graph_engine import get_graph_engine
                from entity.profile_builder import ProfileBuilder
                from memory.versioned_store import get_versioned_store

                graph = get_graph_engine()
                memory = get_versioned_store()
                builder = ProfileBuilder(graph, memory)

                builder.build_or_update_profile(
                    company_id=company_id,
                    extracted_fields=field_results,
                    document_id=document_id,
                    document_type=doc_type.value,
                    filename=filename,
                )
            except Exception as e:
                warnings.append(f"Profile build failed: {e}")

        # ── Stage 8: Audit Trail ─────────────────────────────
        self._write_audit(
            document_id=document_id,
            filename=filename,
            doc_type=doc_type,
            company_id=company_id,
            file_hash=file_hash,
            fields_extracted=len(field_results),
            fields_filled=sum(1 for f in field_results if f.value),
        )

        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "document_id": document_id,
            "status": "completed",
            "filename": filename,
            "document_type": doc_type.value,
            "classification_confidence": class_confidence,
            "chunks_stored": chunks_stored,
            "fields_extracted": len(field_results) if field_results else 0,
            "fields_filled": sum(1 for f in field_results if f.value) if field_results else 0,
            "tables_found": len(tables),
            "layout_elements_found": len(layout_elements),
            "company_id": company_id,
            "file_hash": file_hash,
            "file_size_bytes": file_size,
            "processing_duration_ms": duration_ms,
            "warnings": warnings,
        }

    # ── Pipeline Stages ──────────────────────────────────────

    def _extract_text(self, file_path: str) -> Tuple[list, List[str]]:
        """Stage 2: Extract text from document."""
        warnings = []
        try:
            from rag_pipeline.loader import load_single_doc
            docs = load_single_doc(file_path)
            if not docs:
                warnings.append("All extraction tiers returned empty results")
            return docs, warnings
        except Exception as e:
            warnings.append(f"Text extraction error: {e}")
            return [], warnings

    def _classify(self, filename: str, text: str) -> Tuple[DocumentType, float]:
        """Stage 3: Classify document type."""
        try:
            from ingestion.classifier import get_classifier
            classifier = get_classifier()
            return classifier.classify(filename, text)
        except Exception:
            return DocumentType.UNKNOWN, 0.0

    def _extract_layout(
        self, pdf_path: str, document_id: str,
    ) -> Tuple[list, list, List[str]]:
        """Stage 4: Layout-aware extraction."""
        warnings = []
        try:
            from ingestion.layout_engine import get_layout_engine
            engine = get_layout_engine()

            if engine.is_scanned_pdf(pdf_path):
                elements, tables = engine.extract_from_pdf(pdf_path, document_id)
                return elements, tables, warnings
            else:
                return [], [], warnings

        except Exception as e:
            warnings.append(f"Layout extraction failed: {e}")
            return [], [], warnings

    def _get_memory_values(self, company_id: Optional[str]) -> Dict[str, str]:
        """Get current memory values for a company."""
        if not company_id:
            return {}
        try:
            from entity.graph_engine import get_graph_engine
            graph = get_graph_engine()
            profile = graph.get_company(company_id)
            return profile.to_flat_dict() if profile else {}
        except Exception:
            return {}

    def _write_audit(self, **kwargs):
        """Stage 8: Write audit trail."""
        try:
            from memory.versioned_store import get_audit_writer
            audit = get_audit_writer()
            audit.log(
                action=AuditAction.DOCUMENT_UPLOADED,
                entity_type="document",
                entity_id=kwargs.get("document_id", ""),
                details=kwargs,
            )
        except Exception:
            pass

    @staticmethod
    def _compute_hash(filepath: str) -> str:
        """SHA-256 hash for deduplication."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()






