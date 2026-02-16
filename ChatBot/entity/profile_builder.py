"""
Autonomous Company Profile Builder
====================================
On every document upload:
  1. Extract structured data
  2. Classify document type
  3. Merge into company profile
  4. Deduplicate entities
  5. Resolve conflicts
  6. Update entity graph
  7. Refresh vector memory

Autofill MUST prioritize structured memory over vector search.
"""

import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from core.schemas.company import CompanyProfile
from core.schemas.extraction import FieldResult, CompanyProfileSchema
from core.schemas.enums import DocumentType, ExtractionMethod, ConfidenceLevel
from config.settings import settings


class ProfileBuilder:
    """
    Builds and maintains Master Company Profiles.
    Called automatically on every document upload.
    """

    def __init__(self, graph_engine, versioned_memory):
        self.graph = graph_engine
        self.memory = versioned_memory

    def build_or_update_profile(
        self,
        company_id: str,
        extracted_fields: List[FieldResult],
        document_id: str,
        document_type: str,
        filename: str,
    ) -> CompanyProfile:
        """
        Full profile build/update pipeline.

        Steps:
          1. Get or create company profile
          2. Check for duplicates
          3. Upsert fields with version tracking
          4. Resolve conflicts
          5. Link document to entity graph
          6. Persist to graph + memory
        """
        # Step 1: Get or create
        profile = self.graph.get_company(company_id)
        if profile is None:
            profile = CompanyProfile(company_id=company_id)

        # Step 2: Duplicate check (by EIN or company name)
        ein_field = next((f for f in extracted_fields if f.field_name == "ein" and f.value), None)
        name_field = next((f for f in extracted_fields if f.field_name == "company_name" and f.value), None)

        if ein_field or name_field:
            duplicates = self.graph.find_duplicates(
                ein=ein_field.value if ein_field else None,
                company_name=name_field.value if name_field else None,
            )
            # If we found an existing profile with same EIN, merge into it
            for dup in duplicates:
                if dup.company_id != company_id:
                    print(f"[PROFILE] Duplicate detected: {dup.company_id} ↔ {company_id}")
                    # Use the existing profile as the target
                    profile = dup
                    company_id = dup.company_id
                    break

        # Step 3: Upsert fields with version tracking
        for field in extracted_fields:
            if not field.value or field.confidence < settings.REVIEW_CONFIDENCE_THRESHOLD:
                continue

            change_reason = f"extracted_from_{filename}"
            if field.provenance and field.provenance.validated_by:
                change_reason += f"_validated_by_{field.provenance.validated_by}"

            profile.upsert_field(
                canonical_name=field.field_name,
                value=field.value,
                confidence=field.confidence,
                source_document=filename,
                extraction_method=field.provenance.extraction_method if field.provenance else "llm_structured",
                source_page=field.provenance.page_number if field.provenance else None,
                change_reason=change_reason,
            )

        # Step 4: Link document to entity graph
        if document_id not in profile.linked_documents:
            profile.linked_documents.append(document_id)

        self.graph.link_document(
            company_id=company_id,
            document_id=document_id,
            document_type=document_type,
            filename=filename,
        )

        # Step 5: Persist to graph
        self.graph.upsert_company(profile)

        # Step 6: Persist to versioned memory
        if self.memory:
            self.memory.save_profile_snapshot(company_id, profile)

        return profile

    def get_autofill_values(
        self,
        company_id: str,
        field_names: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get values from structured memory for autofill.
        Returns {field_name: {value, confidence, source}} for each requested field.

        This is called BEFORE vector search — structured memory has priority.
        """
        profile = self.graph.get_company(company_id)
        if not profile:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for field_name in field_names:
            field = profile.fields.get(field_name)
            if field and field.current_value:
                results[field_name] = {
                    "value": field.current_value,
                    "confidence": field.current_confidence,
                    "source": field.current_source,
                    "needs_review": field.needs_review,
                    "conflict": field.conflict_flag,
                }

        return results

    def get_field_history(
        self,
        company_id: str,
        field_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Get full version history for a field.
        Required for compliance audit.
        """
        profile = self.graph.get_company(company_id)
        if not profile:
            return []

        field = profile.fields.get(field_name)
        if not field:
            return []

        return [
            {
                "version": i + 1,
                "value": v.value,
                "confidence": v.confidence,
                "source_document": v.source_document,
                "source_page": v.source_page,
                "extraction_method": v.extraction_method,
                "extracted_at": v.extracted_at.isoformat(),
                "change_reason": v.change_reason,
                "is_active": v.is_active,
            }
            for i, v in enumerate(field.versions)
        ]






