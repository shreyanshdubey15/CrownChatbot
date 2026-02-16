"""
Canonical Enumerations — Entity-Centric Document Intelligence Platform
=======================================================================
All enum types used across the platform.
Strict typing prevents string-based bugs in compliance pipelines.
"""

from enum import Enum


class DocumentType(str, Enum):
    """Document classification categories for telecom compliance."""
    KYC = "kyc"
    AGREEMENT = "agreement"
    INVOICE = "invoice"
    TAX = "tax"
    FCC = "fcc"
    ROBOCALL = "robocall"
    CARRIER_CONTRACT = "carrier_contract"
    AMENDMENT = "amendment"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Confidence classification bands."""
    HIGH = "high"               # >= 0.92 → autofill allowed
    MEDIUM = "medium"           # 0.80 - 0.92 → needs review
    LOW = "low"                 # 0.60 - 0.80 → do not fill
    REJECTED = "rejected"       # < 0.60 → discard

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        if score >= 0.92:
            return cls.HIGH
        elif score >= 0.80:
            return cls.MEDIUM
        elif score >= 0.60:
            return cls.LOW
        return cls.REJECTED


class FieldStatus(str, Enum):
    """Autofill field lifecycle status."""
    FILLED = "filled"                   # Autofilled with high confidence
    NEEDS_REVIEW = "needs_review"       # Below threshold, human review required
    EMPTY = "empty"                     # No data found
    CONFLICT = "conflict"               # Sources disagree
    OVERRIDDEN = "overridden"           # Human manually corrected


class ExtractionMethod(str, Enum):
    """Tracks HOW a value was extracted — critical for audit."""
    LAYOUT_MODEL = "layout_model"           # LayoutLMv3 / Donut
    LLM_STRUCTURED = "llm_structured"       # LLM with JSON schema
    REGEX_VALIDATED = "regex_validated"      # Regex extraction
    TABLE_EXTRACTION = "table_extraction"    # Camelot / Tabula
    OCR_PIPELINE = "ocr_pipeline"           # Tesseract OCR
    STRUCTURED_MEMORY = "structured_memory" # From versioned entity store
    GRAPH_TRAVERSAL = "graph_traversal"     # From Neo4j entity graph
    MANUAL_ENTRY = "manual_entry"           # Human input
    DUAL_LLM_VALIDATED = "dual_llm_validated"  # Passed LLM1→LLM2 pipeline


class EntityRelationType(str, Enum):
    """Relationship types in the entity graph."""
    PARENT_COMPANY = "parent_company"
    SUBSIDIARY = "subsidiary"
    CARRIER_PARTNER = "carrier_partner"
    VENDOR = "vendor"
    REGULATORY_ENTITY = "regulatory_entity"
    FILED_WITH = "filed_with"
    SIGNED_BY = "signed_by"
    REFERENCES = "references"


class AuditAction(str, Enum):
    """Audit trail event types."""
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_CLASSIFIED = "document_classified"
    FIELDS_EXTRACTED = "fields_extracted"
    ENTITY_CREATED = "entity_created"
    ENTITY_UPDATED = "entity_updated"
    ENTITY_MERGED = "entity_merged"
    FIELD_OVERRIDDEN = "field_overridden"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    PROFILE_BUILT = "profile_built"
    FORM_AUTOFILLED = "form_autofilled"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PASSED = "validation_passed"






