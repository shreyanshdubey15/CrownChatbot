"""
Document Schemas — Metadata, Chunks, Layout Elements
=====================================================
Every document ingested into the platform carries rich metadata
for classification, traceability, and audit.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class DocumentMeta(BaseModel):
    """
    Master metadata record for every ingested document.
    Stored alongside the document — never reconstructed.
    """
    document_id: str                                # UUID
    filename: str
    file_extension: str                             # "pdf", "docx", "doc"
    file_size_bytes: int
    file_hash: str                                  # SHA-256 for dedup
    document_type: str                              # DocumentType enum value
    classification_confidence: float = 0.0
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)
    company_id: Optional[str] = None                # Linked entity
    page_count: int = 0
    extraction_method: str = "unknown"
    has_tables: bool = False
    has_images: bool = False
    has_forms: bool = False
    is_scanned: bool = False                        # OCR-routed
    language: str = "en"
    processing_status: str = "pending"              # "pending" | "processing" | "completed" | "failed"
    processing_duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    tags: List[str] = []


class DocumentChunk(BaseModel):
    """
    Enhanced chunk with spatial + provenance metadata.
    Replaces simple text-only chunks.
    """
    chunk_id: str                                   # UUID
    document_id: str                                # Parent document
    text: str
    page_number: int = 1
    chunk_index: int = 0                            # Position within document
    source_filename: str = ""
    # Spatial information (from layout model)
    bbox: Optional[List[float]] = None              # [x0, y0, x1, y1] normalized
    element_type: Optional[str] = None              # "title", "paragraph", "table", "list", "header"
    # Retrieval metadata
    embedding_model: str = ""
    token_count: int = 0
    # Provenance
    extraction_method: str = "text"
    confidence: float = 1.0


class LayoutElement(BaseModel):
    """
    Spatially-aware document element from LayoutLMv3 / Donut.
    Carries bounding box coordinates for field-to-source traceability.
    """
    element_id: str
    document_id: str
    page_number: int
    element_type: str                               # "label", "value", "table_cell", "checkbox", "header"
    text: str
    bbox: List[float]                               # [x0, y0, x1, y1] normalized 0-1
    confidence: float = 0.0
    parent_element_id: Optional[str] = None         # For nested structures
    # Label-value pairing (from layout model)
    linked_label: Optional[str] = None              # If this is a value, what label does it belong to
    linked_value: Optional[str] = None              # If this is a label, what value is associated


class TableData(BaseModel):
    """
    Structured table extracted from a document.
    Each table becomes a JSON object fed into the entity graph.
    """
    table_id: str
    document_id: str
    page_number: int
    headers: List[str] = []
    rows: List[List[str]] = []
    extraction_method: str = "camelot"              # "camelot" | "tabula" | "layout_model"
    confidence: float = 0.0
    bbox: Optional[List[float]] = None

    def to_dict_rows(self) -> List[Dict[str, str]]:
        """Convert table to list of dicts (header → cell value)."""
        if not self.headers:
            return []
        return [
            {h: row[i] if i < len(row) else "" for i, h in enumerate(self.headers)}
            for row in self.rows
        ]

    def to_flat_text(self) -> str:
        """Convert table to searchable flat text."""
        lines = []
        if self.headers:
            lines.append(" | ".join(self.headers))
            lines.append("-" * 40)
        for row in self.rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)


class ExtractionResult(BaseModel):
    """
    Complete extraction result for a single document.
    Contains all extracted fields, tables, and layout elements.
    """
    document_id: str
    document_type: str
    fields: List[Dict[str, Any]] = []               # FieldResult dicts
    tables: List[TableData] = []
    layout_elements: List[LayoutElement] = []
    raw_text: str = ""
    processing_duration_ms: int = 0
    extraction_method: str = ""
    model_used: str = ""
    warnings: List[str] = []






