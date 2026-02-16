"""
API Models — Pydantic Request / Response Schemas
==================================================
All request and response models used by API endpoints.
Centralised here for reuse and clean separation of concerns.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict


# ─────────────────────────────────────────────────────────────
#  CORE / GENERAL
# ─────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str


class MessageResponse(BaseModel):
    message: str


# ─────────────────────────────────────────────────────────────
#  RAG — Ask & Define
# ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class Query(BaseModel):
    question: str = Field(..., json_schema_extra={"example": "What is this document about?"})
    chat_history: Optional[List[ChatMessage]] = Field(
        None, description="Prior conversation turns for context"
    )


class SourceDoc(BaseModel):
    text: str
    source: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[int] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceDoc]


class DefineQuery(BaseModel):
    term: str = Field(..., json_schema_extra={"example": "USF"})


class DefineResponse(BaseModel):
    term: str
    definition: str
    sources: List[SourceDoc]


# ─────────────────────────────────────────────────────────────
#  AUTOFILL
# ─────────────────────────────────────────────────────────────

class AutofillFieldResult(BaseModel):
    field: str
    value: Optional[str] = None
    confidence: float
    source_document: Optional[str] = None
    canonical: Optional[str] = None


class SourceBreakdown(BaseModel):
    memory_only: int = 0
    vector_only: int = 0
    combined_verified: int = 0


class AutofillMetadata(BaseModel):
    total_fields: Optional[int] = None
    filled_fields: Optional[int] = None
    fill_rate: Optional[str] = None
    company_id: Optional[str] = None
    file_id: Optional[str] = None
    file_ext: Optional[str] = None
    error: Optional[str] = None
    source_breakdown: Optional[SourceBreakdown] = None


class AutofillResponse(BaseModel):
    document: str
    fields: List[AutofillFieldResult]
    metadata: Optional[AutofillMetadata] = None


class ProfileFieldDetail(BaseModel):
    value: str
    confidence: float
    source: Optional[str] = None


class BuildProfileRequest(BaseModel):
    company_id: str = Field(..., json_schema_extra={"example": "dorial_telecom"})


class BuildProfileResponse(BaseModel):
    company_id: str
    profile: Dict[str, ProfileFieldDetail]
    fields_extracted: int


class DownloadAutofillRequest(BaseModel):
    document: str = "Autofilled Form"
    fields: List[AutofillFieldResult]
    metadata: Optional[AutofillMetadata] = None


class BatchAutofillFile(BaseModel):
    filename: str
    file_id: str


# ─────────────────────────────────────────────────────────────
#  FEEDBACK
# ─────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    company_id: str
    field_name: str
    original_value: Optional[str] = None
    corrected_value: str
    original_confidence: float = 0.0
    source_document: Optional[str] = None
    user_id: str = "anonymous"
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  TEMPLATES
# ─────────────────────────────────────────────────────────────

class TemplateCreateRequest(BaseModel):
    name: str
    form_type: str = "unknown"
    fields: List[Dict[str, Any]] = []
    file_hash: Optional[str] = None
    description: str = ""


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    form_type: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  APPROVALS
# ─────────────────────────────────────────────────────────────

class ApprovalStepRequest(BaseModel):
    action: str  # "approve", "reject", "request_changes", "final_approve"
    user_id: str = "reviewer"
    comment: Optional[str] = None
    field_corrections: Optional[Dict[str, str]] = None


class ApprovalCreateRequest(BaseModel):
    document_name: str
    company_id: Optional[str] = None
    fields: List[Dict[str, Any]] = []
    file_id: Optional[str] = None
    file_ext: Optional[str] = None
    created_by: str = "system"


# ─────────────────────────────────────────────────────────────
#  SEARCH
# ─────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    company_id: Optional[str] = None
    document_type: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────

class DateNormalizeRequest(BaseModel):
    date_string: str


class AddressStandardizeRequest(BaseModel):
    address: str


# ─────────────────────────────────────────────────────────────
#  RESTRICTED ITEMS
# ─────────────────────────────────────────────────────────────

class RestrictedItemCreate(BaseModel):
    title: str = Field(
        ..., min_length=1,
        json_schema_extra={"example": "Robocalling services"},
    )
    category: str = Field(..., json_schema_extra={"example": "not_provided"})
    description: str = Field(
        "",
        json_schema_extra={"example": "We do not offer any robocalling or auto-dialer services"},
    )
    added_by: str = "admin"
    source_document: Optional[str] = None


class RestrictedItemUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


