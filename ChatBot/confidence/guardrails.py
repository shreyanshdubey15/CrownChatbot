"""
Confidence-Based Autofill Guardrails
======================================
Hard enforcement layer that prevents low-confidence data
from reaching production autofill.

Rules:
  IF confidence >= 0.92 → AUTOFILL (green)
  IF confidence >= 0.80 → NEEDS REVIEW (yellow)
  IF confidence < 0.80  → DO NOT FILL (red)

Every decision carries:
  - confidence score
  - source document
  - page number
  - extraction model
  - validation status

Design: This module is a pure function — no side effects.
        It only classifies and filters.
"""

from typing import List, Dict, Any, Optional
from core.schemas.extraction import FieldResult, FieldProvenance
from core.schemas.enums import ConfidenceLevel, FieldStatus
from config.settings import settings


class ConfidenceGuardrails:
    """
    Enforces confidence thresholds on extraction results.
    Prevents compliance hallucinations.
    """

    def __init__(
        self,
        autofill_threshold: float = None,
        review_threshold: float = None,
    ):
        self.autofill_threshold = autofill_threshold or settings.AUTOFILL_CONFIDENCE_THRESHOLD
        self.review_threshold = review_threshold or settings.REVIEW_CONFIDENCE_THRESHOLD

    def enforce(self, fields: List[FieldResult]) -> List[FieldResult]:
        """
        Apply guardrails to a list of field results.
        Modifies status and value based on confidence thresholds.
        """
        for field in fields:
            field = self._enforce_single(field)
        return fields

    def _enforce_single(self, field: FieldResult) -> FieldResult:
        """Apply guardrails to a single field."""
        if not field.value:
            field.status = FieldStatus.EMPTY.value
            field.confidence_level = ConfidenceLevel.REJECTED.value
            return field

        level = ConfidenceLevel.from_score(field.confidence)
        field.confidence_level = level.value

        if level == ConfidenceLevel.HIGH:
            field.status = FieldStatus.FILLED.value
        elif level == ConfidenceLevel.MEDIUM:
            field.status = FieldStatus.NEEDS_REVIEW.value
        else:
            # Below review threshold — DO NOT FILL
            field.value = None
            field.status = FieldStatus.EMPTY.value

        return field

    def get_autofill_summary(self, fields: List[FieldResult]) -> Dict[str, Any]:
        """
        Generate a summary of guardrail decisions.
        Useful for dashboards and audit reports.
        """
        total = len(fields)
        filled = sum(1 for f in fields if f.status == FieldStatus.FILLED.value)
        needs_review = sum(1 for f in fields if f.status == FieldStatus.NEEDS_REVIEW.value)
        empty = sum(1 for f in fields if f.status == FieldStatus.EMPTY.value)
        conflicts = sum(1 for f in fields if f.status == FieldStatus.CONFLICT.value)

        avg_confidence = 0.0
        if filled > 0:
            avg_confidence = sum(
                f.confidence for f in fields if f.status == FieldStatus.FILLED.value
            ) / filled

        return {
            "total_fields": total,
            "autofilled": filled,
            "needs_review": needs_review,
            "empty": empty,
            "conflicts": conflicts,
            "fill_rate": f"{(filled / total * 100):.1f}%" if total > 0 else "0%",
            "average_confidence": round(avg_confidence, 3),
            "autofill_threshold": self.autofill_threshold,
            "review_threshold": self.review_threshold,
        }

    def get_review_items(self, fields: List[FieldResult]) -> List[Dict[str, Any]]:
        """
        Get all fields that need human review.
        Returns structured data for review UI.
        """
        review_items = []
        for field in fields:
            if field.status in (FieldStatus.NEEDS_REVIEW.value, FieldStatus.CONFLICT.value):
                item = {
                    "field_name": field.field_name,
                    "display_name": field.display_name,
                    "proposed_value": field.extractor_value,
                    "validator_value": field.validator_value,
                    "memory_value": field.memory_value,
                    "confidence": field.confidence,
                    "status": field.status,
                    "values_agree": field.values_agree,
                    "memory_agrees": field.memory_agrees,
                }
                if field.provenance:
                    item["source_document"] = field.provenance.source_document
                    item["page_number"] = field.provenance.page_number
                    item["text_snippet"] = field.provenance.text_snippet
                    item["extraction_model"] = field.provenance.extraction_model

                review_items.append(item)

        return review_items






