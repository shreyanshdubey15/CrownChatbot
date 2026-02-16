"""
Extraction Schemas — Field Results, Provenance, Validation
============================================================
Every extracted field carries a full provenance chain.
This is the audit backbone of the platform.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class FieldProvenance(BaseModel):
    """
    Complete traceability record for a single extracted field.
    Required for FCC / SOX / telecom compliance audit.

    Every filled field MUST have this — no exceptions.
    """
    source_document: str                            # Filename
    source_document_id: str                         # UUID
    page_number: Optional[int] = None
    text_snippet: str = ""                          # Exact text span used
    bbox: Optional[List[float]] = None              # Spatial coordinates
    extraction_model: str = ""                      # "layoutlmv3" | "llama-3.1-70b" | "regex"
    extraction_method: str = ""                     # ExtractionMethod enum value
    confidence: float = 0.0
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    validated_by: Optional[str] = None              # "llm_validator" | "human" | None
    validation_passed: Optional[bool] = None


class FieldResult(BaseModel):
    """
    Single field extraction result with full provenance.
    This is what gets returned to the API consumer.
    """
    field_name: str                                 # Canonical field name
    display_name: str                               # Human-readable label
    value: Optional[str] = None
    confidence: float = 0.0
    confidence_level: str = "rejected"              # ConfidenceLevel enum value
    status: str = "empty"                           # FieldStatus enum value
    provenance: Optional[FieldProvenance] = None
    # Dual-LLM validation
    extractor_value: Optional[str] = None           # LLM #1 output
    validator_value: Optional[str] = None           # LLM #2 output
    values_agree: Optional[bool] = None             # Did both LLMs agree?
    # Memory cross-validation
    memory_value: Optional[str] = None              # From structured memory
    memory_agrees: Optional[bool] = None


class ExtractionRequest(BaseModel):
    """API request for structured extraction."""
    document_id: Optional[str] = None
    document_text: Optional[str] = None
    document_type: Optional[str] = None             # Override auto-classification
    company_id: Optional[str] = None
    target_schema: Optional[str] = None             # "company_profile" | "kyc" | "tax"
    fields_to_extract: Optional[List[str]] = None   # Specific fields, or None for all
    enable_dual_validation: bool = True
    enable_layout_extraction: bool = True


class ExtractionResponse(BaseModel):
    """API response from structured extraction."""
    document_id: str
    document_type: str
    company_id: Optional[str] = None
    fields: List[FieldResult]
    tables_extracted: int = 0
    total_fields: int = 0
    filled_fields: int = 0
    fill_rate: float = 0.0
    needs_review_count: int = 0
    conflict_count: int = 0
    processing_duration_ms: int = 0
    warnings: List[str] = []
    audit_id: Optional[str] = None                  # Links to audit trail


class ValidationResult(BaseModel):
    """
    Result from the dual-LLM validation pipeline.
    LLM #1 extracts → LLM #2 validates → conflicts flagged.
    """
    field_name: str
    extractor_value: Optional[str] = None
    validator_value: Optional[str] = None
    agreement: bool = False
    confidence_adjustment: float = 0.0              # +/- applied to original confidence
    anomaly_detected: bool = False
    anomaly_reason: Optional[str] = None
    validation_model: str = ""
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Telecom-Specific Extraction Schemas ──────────────────────

class CompanyProfileSchema(BaseModel):
    """
    Strict canonical schema for Company Profile extraction.
    LLM MUST output validated JSON matching this shape.
    Replaces all regex-based extraction.
    """
    company_name: Optional[str] = None
    dba: Optional[str] = None
    entity_type: Optional[str] = None
    ein: Optional[str] = None
    fcc_499_id: Optional[str] = None
    frn: Optional[str] = None
    address: Optional[str] = None
    billing_address: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    compliance_contact: Optional[str] = None
    authorized_representative: Optional[str] = None
    title: Optional[str] = None
    state_of_incorporation: Optional[str] = None
    year_incorporated: Optional[str] = None
    traffic_type: Optional[str] = None
    traffic_volume: Optional[str] = None
    ocn: Optional[str] = None
    duns_number: Optional[str] = None
    state_puc_id: Optional[str] = None


class KYCSchema(BaseModel):
    """KYC-specific extraction schema."""
    company_name: Optional[str] = None
    entity_type: Optional[str] = None
    ein: Optional[str] = None
    fcc_499_id: Optional[str] = None
    frn: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    authorized_representative: Optional[str] = None
    title: Optional[str] = None
    state_of_incorporation: Optional[str] = None
    year_incorporated: Optional[str] = None
    traffic_type: Optional[str] = None
    traffic_volume: Optional[str] = None
    ip_addresses: Optional[str] = None
    robocall_mitigation: Optional[str] = None
    stir_shaken_status: Optional[str] = None


class TaxSchema(BaseModel):
    """Tax document extraction schema (499-A / USF)."""
    company_name: Optional[str] = None
    ein: Optional[str] = None
    fcc_499_id: Optional[str] = None
    frn: Optional[str] = None
    revenue_intrastate: Optional[str] = None
    revenue_interstate: Optional[str] = None
    revenue_international: Optional[str] = None
    total_revenue: Optional[str] = None
    filing_period: Optional[str] = None
    authorized_representative: Optional[str] = None


class AgreementSchema(BaseModel):
    """Carrier agreement / contract extraction schema."""
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    effective_date: Optional[str] = None
    termination_date: Optional[str] = None
    traffic_type: Optional[str] = None
    rate_per_minute: Optional[str] = None
    minimum_commitment: Optional[str] = None
    payment_terms: Optional[str] = None
    jurisdiction: Optional[str] = None
    governing_law: Optional[str] = None


# Schema registry — maps DocumentType to extraction schema
SCHEMA_REGISTRY: Dict[str, type] = {
    "kyc": KYCSchema,
    "tax": TaxSchema,
    "agreement": AgreementSchema,
    "carrier_contract": AgreementSchema,
    "fcc": TaxSchema,
    "company_profile": CompanyProfileSchema,
}






