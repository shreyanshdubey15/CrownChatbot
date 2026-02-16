"""
Schema-Based Structured Extraction Engine
==========================================
Replaces all regex-based extraction with strict canonical schemas.
Forces the LLM to output VALIDATED JSON matching Pydantic models.
Unstructured text responses are NOT allowed.

Routes each document type to its specialized schema:
  KYC → KYCSchema
  Tax → TaxSchema
  Agreement → AgreementSchema
  Default → CompanyProfileSchema

Architecture:
  1. Classify document type
  2. Select extraction schema
  3. Build schema-aware prompt
  4. LLM → structured JSON
  5. Pydantic validation
  6. Dual-LLM validation (optional)
  7. Confidence guardrails
"""

import json
import asyncio
from typing import Optional, List, Dict, Any
from core.schemas.extraction import (
    FieldResult, ExtractionResponse,
    CompanyProfileSchema, KYCSchema, TaxSchema, AgreementSchema,
    SCHEMA_REGISTRY,
)
from core.schemas.enums import DocumentType, ConfidenceLevel, FieldStatus
from extraction.dual_llm_validator import DualLLMValidator
from config.settings import settings


class SchemaExtractor:
    """
    Schema-driven extraction engine.
    Forces LLM output to match Pydantic schemas — no free-text allowed.
    """

    def __init__(self, dual_validator: Optional[DualLLMValidator] = None):
        self.validator = dual_validator

    async def extract(
        self,
        text: str,
        document_type: str,
        document_id: str = "",
        source_document: str = "",
        company_id: Optional[str] = None,
        memory_values: Optional[Dict[str, str]] = None,
        enable_dual_validation: bool = True,
    ) -> ExtractionResponse:
        """
        Full schema-based extraction pipeline.

        1. Select schema based on document type
        2. Extract all fields via dual-LLM pipeline
        3. Validate against schema
        4. Return typed ExtractionResponse
        """
        import time
        start = time.time()

        # Step 1: Get the right schema
        schema_class = SCHEMA_REGISTRY.get(document_type, CompanyProfileSchema)
        schema_fields = self._get_schema_fields(schema_class)

        # Step 2: Prepare fields with memory hints
        fields_to_extract = []
        for field_name, field_info in schema_fields.items():
            display_name = field_name.replace("_", " ").title()
            memory_value = None
            if memory_values and field_name in memory_values:
                memory_value = memory_values[field_name]

            fields_to_extract.append({
                "canonical_name": field_name,
                "display_name": display_name,
                "memory_value": memory_value,
            })

        # Step 3: Extract via dual-LLM pipeline
        if enable_dual_validation and self.validator:
            context = self._build_context(text)
            field_results = await self.validator.extract_and_validate_batch(
                fields=fields_to_extract,
                context=context,
                source_document=source_document,
                document_id=document_id,
            )
        else:
            field_results = []
            for field in fields_to_extract:
                field_results.append(FieldResult(
                    field_name=field["canonical_name"],
                    display_name=field["display_name"],
                    value=None,
                    confidence=0.0,
                    confidence_level=ConfidenceLevel.REJECTED.value,
                    status=FieldStatus.EMPTY.value,
                ))

        # Step 4: Apply confidence guardrails
        for result in field_results:
            if result.confidence < settings.AUTOFILL_CONFIDENCE_THRESHOLD:
                if result.confidence >= settings.REVIEW_CONFIDENCE_THRESHOLD:
                    result.status = FieldStatus.NEEDS_REVIEW.value
                else:
                    result.status = FieldStatus.EMPTY.value
                    result.value = None  # Do NOT autofill below threshold

        # Compute stats
        filled = sum(1 for r in field_results if r.value is not None)
        needs_review = sum(1 for r in field_results if r.status == FieldStatus.NEEDS_REVIEW.value)
        conflicts = sum(1 for r in field_results if r.status == FieldStatus.CONFLICT.value)
        total = len(field_results)

        duration_ms = int((time.time() - start) * 1000)

        return ExtractionResponse(
            document_id=document_id,
            document_type=document_type,
            company_id=company_id,
            fields=field_results,
            total_fields=total,
            filled_fields=filled,
            fill_rate=round(filled / total * 100, 1) if total > 0 else 0.0,
            needs_review_count=needs_review,
            conflict_count=conflicts,
            processing_duration_ms=duration_ms,
        )

    def _get_schema_fields(self, schema_class) -> Dict[str, Any]:
        """Extract field names and types from a Pydantic schema."""
        fields = {}
        for field_name, field_info in schema_class.model_fields.items():
            fields[field_name] = {
                "type": str(field_info.annotation),
                "required": field_info.is_required(),
            }
        return fields

    def _build_context(self, text: str) -> str:
        """Build extraction context from document text."""
        # Truncate to stay within LLM context window
        max_context = 12000
        if len(text) > max_context:
            # Take beginning and end (important data often at both)
            half = max_context // 2
            text = text[:half] + "\n\n[...TRUNCATED...]\n\n" + text[-half:]
        return text






