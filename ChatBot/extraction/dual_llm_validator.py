"""
Dual-LLM Validator Agent — Anti-Hallucination Layer
=====================================================
REQUIRED for compliance-grade AI.

Pipeline:
  LLM #1 (Primary, larger) → Extract field values
  LLM #2 (Validator, smaller) → Independently validate

Agreement → High confidence
Disagreement → Flag anomaly, reduce confidence

This eliminates single-model hallucination risk.
Both models MUST agree for a value to be autofilled.

Architecture:
  - LLM #1: llama-3.1-70b-versatile (extraction)
  - LLM #2: llama-3.1-8b-instant (validation)
  - Both operate on the SAME context
  - Results cross-validated field-by-field
"""

import re
import json
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from config.settings import settings
from rag_pipeline.llm_client import get_async_client, get_model
from core.schemas.extraction import ValidationResult, FieldResult, FieldProvenance
from core.schemas.enums import ConfidenceLevel, FieldStatus, ExtractionMethod


class DualLLMValidator:
    """
    Dual-LLM extraction + validation pipeline.
    LLM #1 extracts. LLM #2 validates. Conflicts flagged.
    """

    def __init__(self):
        self.groq = get_async_client()
        self.primary_model = get_model("primary")
        self.validator_model = get_model("validator")

    async def extract_and_validate(
        self,
        field_name: str,
        field_display_name: str,
        context: str,
        source_document: str = "",
        document_id: str = "",
        page_number: Optional[int] = None,
        memory_value: Optional[str] = None,
    ) -> FieldResult:
        """
        Full dual-LLM pipeline for a single field.

        1. LLM #1 extracts value from context
        2. LLM #2 independently validates
        3. Cross-validate results
        4. Compute final confidence
        """
        # Step 1: Primary extraction (larger model)
        extractor_result = await self._extract(
            field_name=field_name,
            field_display_name=field_display_name,
            context=context,
            model=self.primary_model,
            memory_hint=memory_value,
        )

        extractor_value = extractor_result.get("value")
        extractor_confidence = extractor_result.get("confidence", 0.0)
        extractor_snippet = extractor_result.get("text_snippet", "")

        # Step 2: Validation (smaller model, independent)
        validator_result = await self._validate(
            field_name=field_name,
            field_display_name=field_display_name,
            proposed_value=extractor_value,
            context=context,
            model=self.validator_model,
        )

        validator_value = validator_result.get("value")
        validator_agrees = validator_result.get("agrees", False)
        validator_confidence = validator_result.get("confidence", 0.0)
        anomaly_reason = validator_result.get("anomaly_reason")

        # Step 3: Cross-validate
        values_agree = self._check_agreement(extractor_value, validator_value)

        # Step 4: Compute final confidence
        final_confidence = self._compute_final_confidence(
            extractor_confidence=extractor_confidence,
            validator_confidence=validator_confidence,
            values_agree=values_agree,
            validator_agrees=validator_agrees,
            memory_value=memory_value,
            extracted_value=extractor_value,
        )

        # Determine status
        confidence_level = ConfidenceLevel.from_score(final_confidence)
        if not extractor_value:
            status = FieldStatus.EMPTY
        elif not values_agree:
            status = FieldStatus.CONFLICT
        elif confidence_level == ConfidenceLevel.HIGH:
            status = FieldStatus.FILLED
        elif confidence_level == ConfidenceLevel.MEDIUM:
            status = FieldStatus.NEEDS_REVIEW
        else:
            status = FieldStatus.EMPTY

        # Build provenance
        provenance = FieldProvenance(
            source_document=source_document,
            source_document_id=document_id,
            page_number=page_number,
            text_snippet=extractor_snippet,
            extraction_model=self.primary_model,
            extraction_method=ExtractionMethod.DUAL_LLM_VALIDATED.value,
            confidence=final_confidence,
            validated_by=self.validator_model,
            validation_passed=values_agree and validator_agrees,
        )

        # Use extractor value if agreement, otherwise flag conflict
        final_value = extractor_value if values_agree else None

        return FieldResult(
            field_name=field_name,
            display_name=field_display_name,
            value=final_value,
            confidence=final_confidence,
            confidence_level=confidence_level.value,
            status=status.value,
            provenance=provenance,
            extractor_value=extractor_value,
            validator_value=validator_value,
            values_agree=values_agree,
            memory_value=memory_value,
            memory_agrees=self._check_agreement(extractor_value, memory_value) if memory_value else None,
        )

    async def extract_and_validate_batch(
        self,
        fields: List[Dict[str, Any]],
        context: str,
        source_document: str = "",
        document_id: str = "",
    ) -> List[FieldResult]:
        """
        Process multiple fields in parallel through the dual-LLM pipeline.
        Each field runs extract + validate concurrently.
        """
        tasks = [
            self.extract_and_validate(
                field_name=f["canonical_name"],
                field_display_name=f["display_name"],
                context=context,
                source_document=source_document,
                document_id=document_id,
                page_number=f.get("page_number"),
                memory_value=f.get("memory_value"),
            )
            for f in fields
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        field_results: List[FieldResult] = []
        for field, result in zip(fields, results):
            if isinstance(result, BaseException):
                print(f"[VALIDATOR] Error on field '{field['canonical_name']}': {result}")
                field_results.append(FieldResult(
                    field_name=field["canonical_name"],
                    display_name=field["display_name"],
                    value=None,
                    confidence=0.0,
                    confidence_level=ConfidenceLevel.REJECTED.value,
                    status=FieldStatus.EMPTY.value,
                ))
            else:
                field_results.append(result)

        return field_results

    # ── LLM Calls ────────────────────────────────────────────

    async def _extract(
        self,
        field_name: str,
        field_display_name: str,
        context: str,
        model: str,
        memory_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """LLM #1: Primary extraction."""
        memory_section = ""
        if memory_hint:
            memory_section = (
                f"\nPREVIOUSLY KNOWN VALUE (verify against context): \"{memory_hint}\"\n"
                "Use ONLY if confirmed by the context above.\n"
            )

        prompt = (
            "You are a compliance-grade document extraction engine for telecom regulatory documents.\n\n"
            "ABSOLUTE RULES:\n"
            "- Extract ONLY from the provided context\n"
            "- Do NOT infer, guess, or hallucinate\n"
            "- If the value is not clearly present → return null\n"
            "- Prefer EXACT text spans from the context\n"
            "- Output VALID JSON only — no markdown, no explanation\n\n"
            f"FIELD TO EXTRACT:\n"
            f"  Name: {field_display_name}\n"
            f"  Canonical: {field_name}\n"
            f"{memory_section}\n"
            f"CONTEXT:\n{context[:8000]}\n\n"
            "Return ONLY this JSON:\n"
            '{"value": "<extracted value or null>", '
            '"confidence": <float 0.0 to 1.0>, '
            '"text_snippet": "<exact text span used for extraction>"}'
        )

        try:
            response = await self.groq.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS_EXTRACT,
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_json_response(raw)

        except Exception as e:
            print(f"[EXTRACTOR] Failed for '{field_name}': {e}")
            return {"value": None, "confidence": 0.0, "text_snippet": ""}

    async def _validate(
        self,
        field_name: str,
        field_display_name: str,
        proposed_value: Optional[str],
        context: str,
        model: str,
    ) -> Dict[str, Any]:
        """
        LLM #2: Independent validation.
        Given a proposed value, verify it exists in the context.
        """
        if not proposed_value:
            return {"value": None, "agrees": True, "confidence": 0.0}

        prompt = (
            "You are a compliance validation engine. Your job is to VERIFY extracted data.\n\n"
            "RULES:\n"
            "- Check if the proposed value actually appears in the context\n"
            "- If the value is correct → agrees: true\n"
            "- If the value is wrong, fabricated, or not in context → agrees: false\n"
            "- If you can find a better/more accurate value → provide it\n"
            "- Flag any anomalies (wrong format, impossible values, etc.)\n"
            "- Output VALID JSON only\n\n"
            f"FIELD: {field_display_name} ({field_name})\n"
            f"PROPOSED VALUE: \"{proposed_value}\"\n\n"
            f"CONTEXT:\n{context[:6000]}\n\n"
            "Return ONLY this JSON:\n"
            '{"value": "<your verified value or null>", '
            '"agrees": <true/false>, '
            '"confidence": <float 0.0 to 1.0>, '
            '"anomaly_reason": "<reason if anomaly detected, else null>"}'
        )

        try:
            response = await self.groq.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS_VALIDATE,
            )
            raw = response.choices[0].message.content.strip()
            return self._parse_json_response(raw)

        except Exception as e:
            print(f"[VALIDATOR] Failed for '{field_name}': {e}")
            return {"value": None, "agrees": False, "confidence": 0.0}

    # ── Helpers ──────────────────────────────────────────────

    def _parse_json_response(self, raw: str) -> Dict[str, Any]:
        """Parse LLM JSON response with error handling."""
        try:
            match = re.search(r"\{[\s\S]*?\}", raw)
            if match:
                result = json.loads(match.group())
                # Normalize null strings
                if isinstance(result.get("value"), str) and result["value"].strip().lower() == "null":
                    result["value"] = None
                return result
        except json.JSONDecodeError:
            pass
        return {"value": None, "confidence": 0.0}

    def _check_agreement(
        self,
        value_a: Optional[str],
        value_b: Optional[str],
    ) -> bool:
        """Check if two values agree (exact or fuzzy)."""
        if value_a is None and value_b is None:
            return True
        if value_a is None or value_b is None:
            return False

        a = value_a.lower().strip()
        b = value_b.lower().strip()

        # Exact match
        if a == b:
            return True

        # Substring match (one contains the other)
        if a in b or b in a:
            return True

        # Normalized match (remove punctuation)
        a_clean = re.sub(r"[^a-z0-9]", "", a)
        b_clean = re.sub(r"[^a-z0-9]", "", b)
        if a_clean == b_clean:
            return True

        return False

    def _compute_final_confidence(
        self,
        extractor_confidence: float,
        validator_confidence: float,
        values_agree: bool,
        validator_agrees: bool,
        memory_value: Optional[str],
        extracted_value: Optional[str],
    ) -> float:
        """
        Multi-signal confidence computation.
        Agreement between LLMs + memory = highest confidence.
        """
        if not extracted_value:
            return 0.0

        # Base: average of both LLM confidences
        base = (extractor_confidence + validator_confidence) / 2.0

        # Agreement boost
        if values_agree and validator_agrees:
            base = min(base + settings.MEMORY_AGREEMENT_BOOST, 1.0)
        elif not values_agree:
            base = max(base - settings.CONTRADICTION_PENALTY, 0.0)
        elif not validator_agrees:
            base = max(base - settings.CONTRADICTION_PENALTY * 0.5, 0.0)

        # Memory cross-validation
        if memory_value and extracted_value:
            if self._check_agreement(extracted_value, memory_value):
                base = min(base + settings.MEMORY_AGREEMENT_BOOST, 1.0)
            else:
                # Memory disagrees — could be stale, slight penalty
                base = max(base - 0.05, 0.0)

        return round(base, 3)


# Module-level singleton
_validator: Optional[DualLLMValidator] = None


def get_dual_validator() -> DualLLMValidator:
    global _validator
    if _validator is None:
        _validator = DualLLMValidator()
    return _validator


