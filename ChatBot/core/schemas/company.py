"""
Canonical Company Schemas — Master Entity Model
=================================================
Replaces flat JSON memory with a versioned, traceable entity model.
Every field carries full provenance chain.

Design: Temporal data model — no overwrites, append-only history.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CompanyFieldVersion(BaseModel):
    """
    A single version of a company field value.
    Append-only — NEVER delete previous versions.
    Banks and FCC auditors require full history.
    """
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_document: str
    source_page: Optional[int] = None
    extraction_method: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    extracted_by: str = "system"                    # "system" | user_id
    change_reason: Optional[str] = None             # "initial_extraction" | "updated_from_new_doc" | "manual_override"
    is_active: bool = True                          # Only one active version per field

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CompanyField(BaseModel):
    """
    A company field with full version history.
    Current value = latest active version.
    Supports rollback by deactivating current + reactivating previous.
    """
    canonical_name: str                             # e.g. "ein", "company_name"
    display_name: str                               # e.g. "Federal Tax ID (EIN)"
    versions: List[CompanyFieldVersion] = []
    conflict_flag: bool = False                     # True if sources disagree
    needs_review: bool = False

    @property
    def current_value(self) -> Optional[str]:
        active = [v for v in self.versions if v.is_active]
        return active[-1].value if active else None

    @property
    def current_confidence(self) -> float:
        active = [v for v in self.versions if v.is_active]
        return active[-1].confidence if active else 0.0

    @property
    def current_source(self) -> Optional[str]:
        active = [v for v in self.versions if v.is_active]
        return active[-1].source_document if active else None

    def add_version(
        self,
        value: str,
        confidence: float,
        source_document: str,
        extraction_method: str,
        source_page: Optional[int] = None,
        change_reason: str = "updated_from_new_doc",
    ) -> None:
        """Append a new version. Deactivate previous active versions."""
        # Check for conflict
        if self.current_value and self.current_value.lower().strip() != value.lower().strip():
            if confidence < self.current_confidence:
                # New value is lower confidence — flag conflict but keep current
                self.conflict_flag = True
                self.needs_review = True
                # Still store as inactive version for audit
                self.versions.append(CompanyFieldVersion(
                    value=value,
                    confidence=confidence,
                    source_document=source_document,
                    source_page=source_page,
                    extraction_method=extraction_method,
                    change_reason=f"conflict_lower_confidence: {change_reason}",
                    is_active=False,
                ))
                return

        # Deactivate all previous versions
        for v in self.versions:
            v.is_active = False

        # Append new active version
        self.versions.append(CompanyFieldVersion(
            value=value,
            confidence=confidence,
            source_document=source_document,
            source_page=source_page,
            extraction_method=extraction_method,
            change_reason=change_reason,
            is_active=True,
        ))
        self.conflict_flag = False

    def rollback(self, version_index: int) -> bool:
        """Rollback to a specific version by index."""
        if version_index < 0 or version_index >= len(self.versions):
            return False
        for v in self.versions:
            v.is_active = False
        self.versions[version_index].is_active = True
        return True


class CompanyProfile(BaseModel):
    """
    Master Company Profile — the ENTITY, not the document.
    Central node in the entity graph.

    Canonical fields aligned with telecom compliance requirements:
    KYC + FCC + Tax + Carrier Agreement coverage.
    """
    company_id: str                                 # Deterministic slug: "dorial_telecom"
    fields: Dict[str, CompanyField] = {}
    linked_documents: List[str] = []                # Document IDs that contributed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_verified: bool = False                       # Human-verified flag
    tags: List[str] = []                            # ["carrier", "voip", "clec"]

    # ── Canonical field registry ────────────────────────────
    CANONICAL_FIELDS: Dict[str, str] = {
        "company_name": "Registered Business Name",
        "dba": "Doing Business As (DBA)",
        "entity_type": "Entity Type",
        "ein": "Federal Tax ID (EIN)",
        "fcc_499_id": "FCC 499 ID",
        "frn": "FCC Registration Number (FRN)",
        "address": "Business Address",
        "billing_address": "Billing Address",
        "phone": "Phone Number",
        "fax": "Fax Number",
        "email": "Email Address",
        "website": "Website",
        "compliance_contact": "Compliance Contact",
        "authorized_representative": "Authorized Representative",
        "title": "Title / Position",
        "state_of_incorporation": "State of Incorporation",
        "year_incorporated": "Year Incorporated",
        "traffic_type": "Traffic Type",
        "traffic_volume": "Traffic Volume",
        "ip_addresses": "IP Addresses",
        "ocn": "Operating Company Number (OCN)",
        "duns_number": "DUNS Number",
        "state_puc_id": "State PUC ID",
        "robocall_mitigation": "Robocall Mitigation Status",
        "stir_shaken_status": "STIR/SHAKEN Implementation",
    }

    def upsert_field(
        self,
        canonical_name: str,
        value: str,
        confidence: float,
        source_document: str,
        extraction_method: str,
        source_page: Optional[int] = None,
        change_reason: str = "updated_from_new_doc",
    ) -> None:
        """Upsert a field with full version tracking."""
        if canonical_name not in self.fields:
            display = self.CANONICAL_FIELDS.get(canonical_name, canonical_name)
            self.fields[canonical_name] = CompanyField(
                canonical_name=canonical_name,
                display_name=display,
            )

        self.fields[canonical_name].add_version(
            value=value,
            confidence=confidence,
            source_document=source_document,
            extraction_method=extraction_method,
            source_page=source_page,
            change_reason=change_reason,
        )
        self.updated_at = datetime.utcnow()

    def get_field_value(self, canonical_name: str) -> Optional[str]:
        """Get current active value for a field."""
        field = self.fields.get(canonical_name)
        return field.current_value if field else None

    def get_field_history(self, canonical_name: str) -> List[CompanyFieldVersion]:
        """Get full version history for audit."""
        field = self.fields.get(canonical_name)
        return field.versions if field else []

    def get_conflicts(self) -> Dict[str, CompanyField]:
        """Get all fields with active conflicts."""
        return {k: v for k, v in self.fields.items() if v.conflict_flag}

    def get_needs_review(self) -> Dict[str, CompanyField]:
        """Get all fields requiring human review."""
        return {k: v for k, v in self.fields.items() if v.needs_review}

    def to_flat_dict(self) -> Dict[str, Any]:
        """Export as flat key-value dict (for backward compat)."""
        return {
            k: v.current_value
            for k, v in self.fields.items()
            if v.current_value
        }


class CompanyNode(BaseModel):
    """Node representation for the entity graph (Neo4j)."""
    company_id: str
    company_name: Optional[str] = None
    ein: Optional[str] = None
    fcc_499_id: Optional[str] = None
    entity_type: Optional[str] = None
    properties: Dict[str, Any] = {}


class CompanyRelationship(BaseModel):
    """Edge in the entity graph."""
    source_company_id: str
    target_company_id: str
    relationship_type: str                          # EntityRelationType value
    source_document: Optional[str] = None
    confidence: float = 0.0
    properties: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)






