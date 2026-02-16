"""
Automatic Document Classifier — High ROI Pre-Extraction Routing
================================================================
Classifies every uploaded document BEFORE extraction begins.
Routes each type to its specialized extractor + schema.

Strategies (cascading):
  1. Filename heuristics (fast, zero-cost)
  2. Content keyword scoring (fast, rule-based)
  3. LLM zero-shot classification (accurate, costs tokens)

Design: The classifier NEVER modifies the document.
        It only produces a DocumentType + confidence score.
"""

import re
import os
from typing import Tuple, Optional
from config.settings import settings
from rag_pipeline.llm_client import get_sync_client, get_model
from core.schemas.enums import DocumentType


# ── Filename Patterns ───────────────────────────────────────
# High-precision patterns mined from real telecom document naming conventions.
FILENAME_PATTERNS: dict[DocumentType, list[re.Pattern]] = {
    DocumentType.KYC: [
        re.compile(r"kyc", re.IGNORECASE),
        re.compile(r"know\s*your\s*cust", re.IGNORECASE),
        re.compile(r"customer\s*form", re.IGNORECASE),
        re.compile(r"client\s*identification", re.IGNORECASE),
    ],
    DocumentType.TAX: [
        re.compile(r"tax", re.IGNORECASE),
        re.compile(r"499[-\s]?[aA]", re.IGNORECASE),
        re.compile(r"usf", re.IGNORECASE),
        re.compile(r"w[-\s]?9", re.IGNORECASE),
    ],
    DocumentType.FCC: [
        re.compile(r"fcc", re.IGNORECASE),
        re.compile(r"499\s*form", re.IGNORECASE),
        re.compile(r"frn", re.IGNORECASE),
    ],
    DocumentType.AGREEMENT: [
        re.compile(r"agreement", re.IGNORECASE),
        re.compile(r"contract", re.IGNORECASE),
        re.compile(r"service\s*agreement", re.IGNORECASE),
        re.compile(r"master\s*service", re.IGNORECASE),
    ],
    DocumentType.CARRIER_CONTRACT: [
        re.compile(r"carrier", re.IGNORECASE),
        re.compile(r"interconnect", re.IGNORECASE),
        re.compile(r"wholesale", re.IGNORECASE),
    ],
    DocumentType.ROBOCALL: [
        re.compile(r"robocall", re.IGNORECASE),
        re.compile(r"stir.?shaken", re.IGNORECASE),
        re.compile(r"call\s*mitigation", re.IGNORECASE),
        re.compile(r"dialer", re.IGNORECASE),
        re.compile(r"short\s*duration", re.IGNORECASE),
    ],
    DocumentType.INVOICE: [
        re.compile(r"invoice", re.IGNORECASE),
        re.compile(r"billing", re.IGNORECASE),
        re.compile(r"payment", re.IGNORECASE),
    ],
    DocumentType.AMENDMENT: [
        re.compile(r"addendum", re.IGNORECASE),
        re.compile(r"amendment", re.IGNORECASE),
        re.compile(r"modification", re.IGNORECASE),
    ],
}


# ── Content Keyword Scoring ─────────────────────────────────
# Weighted keyword sets for content-based classification.
# Score = sum(weights) for matched keywords.
CONTENT_KEYWORDS: dict[DocumentType, dict[str, float]] = {
    DocumentType.KYC: {
        "know your customer": 3.0,
        "kyc": 3.0,
        "entity type": 2.0,
        "ein": 1.5,
        "authorized representative": 2.0,
        "business address": 1.5,
        "traffic type": 2.0,
        "ip address": 1.5,
        "wholesale": 1.0,
        "dba": 1.0,
        "state of incorporation": 1.5,
    },
    DocumentType.TAX: {
        "tax": 2.0,
        "499-a": 3.0,
        "usf": 2.5,
        "universal service fund": 3.0,
        "filer id": 2.0,
        "revenue": 2.0,
        "intrastate": 2.0,
        "interstate": 2.0,
        "contribution": 1.5,
        "filing period": 2.0,
    },
    DocumentType.FCC: {
        "fcc": 3.0,
        "federal communications commission": 3.0,
        "499": 2.0,
        "frn": 2.0,
        "fcc registration": 2.5,
        "telecommunications": 1.5,
    },
    DocumentType.AGREEMENT: {
        "agreement": 2.0,
        "terms and conditions": 2.5,
        "shall": 1.0,
        "party": 1.5,
        "effective date": 2.0,
        "termination": 1.5,
        "governing law": 2.0,
        "indemnification": 1.5,
        "confidential": 1.0,
    },
    DocumentType.ROBOCALL: {
        "robocall": 3.0,
        "stir/shaken": 3.0,
        "stir shaken": 3.0,
        "call mitigation": 2.5,
        "illegal robocall": 2.5,
        "traced": 1.5,
        "dialer": 2.0,
        "short duration": 2.0,
        "cps": 1.5,
    },
    DocumentType.INVOICE: {
        "invoice": 3.0,
        "amount due": 2.5,
        "billing": 2.0,
        "payment": 1.5,
        "due date": 2.0,
        "total": 1.0,
        "subtotal": 1.5,
    },
    DocumentType.CARRIER_CONTRACT: {
        "carrier": 2.0,
        "interconnect": 2.5,
        "wholesale": 2.0,
        "rate deck": 2.5,
        "per minute": 2.0,
        "origination": 1.5,
        "termination": 1.5,
        "trunk": 1.5,
    },
    DocumentType.AMENDMENT: {
        "addendum": 3.0,
        "amendment": 3.0,
        "modification": 2.0,
        "hereby amended": 2.5,
        "supplemental": 2.0,
    },
}


class DocumentClassifier:
    """
    Multi-strategy document classifier.
    Cascading: filename → content keywords → LLM zero-shot.
    Returns (DocumentType, confidence).
    """

    def __init__(self):
        self._llm_client = None

    @property
    def groq_client(self):
        if self._llm_client is None:
            self._llm_client = get_sync_client()
        return self._llm_client

    def classify(
        self,
        filename: str,
        text_content: str = "",
        use_llm_fallback: bool = True,
    ) -> Tuple[DocumentType, float]:
        """
        Classify a document using cascading strategies.

        Returns:
            (DocumentType, confidence: float)
        """
        # ── Strategy 1: Filename heuristics (free, instant) ──
        doc_type, conf = self._classify_by_filename(filename)
        if conf >= 0.85:
            return doc_type, conf

        # ── Strategy 2: Content keyword scoring (free, fast) ──
        if text_content:
            content_type, content_conf = self._classify_by_content(text_content)
            if content_conf >= 0.75:
                # If filename gave a weak signal, combine
                if doc_type == content_type:
                    return doc_type, min(conf + content_conf, 1.0)
                return content_type, content_conf

        # ── Strategy 3: LLM zero-shot (costs tokens, most accurate) ──
        if use_llm_fallback and text_content:
            llm_type, llm_conf = self._classify_by_llm(text_content)
            if llm_conf >= 0.60:
                return llm_type, llm_conf

        # Fallback: return best heuristic or unknown
        if conf > 0.0:
            return doc_type, conf
        return DocumentType.UNKNOWN, 0.0

    def _classify_by_filename(self, filename: str) -> Tuple[DocumentType, float]:
        """Score filename against known patterns."""
        base = os.path.basename(filename)
        best_type = DocumentType.UNKNOWN
        best_score = 0.0

        for doc_type, patterns in FILENAME_PATTERNS.items():
            score = sum(1.0 for p in patterns if p.search(base))
            normalized = min(score / 2.0, 1.0)  # 2+ matches = high confidence
            if normalized > best_score:
                best_score = normalized
                best_type = doc_type

        return best_type, round(best_score, 2)

    def _classify_by_content(self, text: str) -> Tuple[DocumentType, float]:
        """Score content against weighted keyword sets."""
        text_lower = text.lower()
        scores: dict[DocumentType, float] = {}

        for doc_type, keywords in CONTENT_KEYWORDS.items():
            score = sum(
                weight for keyword, weight in keywords.items()
                if keyword in text_lower
            )
            scores[doc_type] = score

        if not scores or max(scores.values()) == 0:
            return DocumentType.UNKNOWN, 0.0

        best_type = max(scores, key=scores.get)  # type: ignore
        best_score = scores[best_type]

        # Normalize: 8+ points = very confident, scale to 0-1
        max_possible = max(
            sum(v for v in kw.values())
            for kw in CONTENT_KEYWORDS.values()
        )
        confidence = min(best_score / (max_possible * 0.4), 1.0)

        return best_type, round(confidence, 2)

    def _classify_by_llm(self, text: str) -> Tuple[DocumentType, float]:
        """Zero-shot LLM classification. Most accurate, costs tokens."""
        text_truncated = text[:4000]
        valid_types = ", ".join([t.value for t in DocumentType])

        prompt = (
            "You are a document classification engine for telecom compliance.\n\n"
            "TASK: Classify this document into ONE category.\n\n"
            f"VALID CATEGORIES: {valid_types}\n\n"
            "RULES:\n"
            "- Return ONLY valid JSON\n"
            "- Choose the SINGLE best category\n"
            "- Confidence must be 0.0 to 1.0\n\n"
            f"DOCUMENT TEXT (first 4000 chars):\n{text_truncated}\n\n"
            'Return: {"document_type": "<category>", "confidence": <float>}'
        )

        try:
            response = self.groq_client.chat.completions.create(
                model=get_model("classifier"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=128,
            )
            raw = response.choices[0].message.content.strip()

            import json
            match = re.search(r"\{[\s\S]*?\}", raw)
            if match:
                result = json.loads(match.group())
                doc_type_str = result.get("document_type", "unknown")
                confidence = float(result.get("confidence", 0.0))

                try:
                    doc_type = DocumentType(doc_type_str)
                except ValueError:
                    doc_type = DocumentType.UNKNOWN
                    confidence *= 0.5

                return doc_type, round(confidence, 2)

        except Exception as e:
            print(f"[CLASSIFIER] LLM classification failed: {e}")

        return DocumentType.UNKNOWN, 0.0


# Module-level singleton
_classifier: Optional[DocumentClassifier] = None


def get_classifier() -> DocumentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = DocumentClassifier()
    return _classifier


