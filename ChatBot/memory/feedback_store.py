"""
Active Learning Feedback Store
================================
When users manually correct an autofill value, the correction
is stored and used to improve future extractions.

Pipeline:
  1. User corrects a field value in the review UI
  2. Correction is logged with provenance (who, when, original vs corrected)
  3. On next extraction, feedback is injected as a hint
  4. Over time, the system learns per-field correction patterns

Storage: JSONL append-only log (production: PostgreSQL)
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config.settings import settings


class FeedbackStore:
    """
    Append-only feedback store for user corrections.
    Used by the autofill engine to improve future extractions.
    """

    def __init__(self):
        self._store_path = os.path.join(settings.MEMORY_STORE_PATH, "feedback")
        os.makedirs(self._store_path, exist_ok=True)

    def log_correction(
        self,
        company_id: str,
        field_name: str,
        original_value: Optional[str],
        corrected_value: str,
        original_confidence: float,
        source_document: Optional[str] = None,
        user_id: str = "anonymous",
        notes: Optional[str] = None,
    ) -> str:
        """
        Log a user correction for a field.
        Returns feedback_id.
        """
        import uuid

        feedback_id = str(uuid.uuid4())
        entry = {
            "feedback_id": feedback_id,
            "company_id": company_id,
            "field_name": field_name,
            "original_value": original_value,
            "corrected_value": corrected_value,
            "original_confidence": original_confidence,
            "source_document": source_document,
            "user_id": user_id,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat(),
        }

        log_file = os.path.join(self._store_path, f"{company_id}_feedback.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Update the correction index for fast lookup
        self._update_correction_index(field_name, original_value, corrected_value)

        return feedback_id

    def get_corrections_for_field(
        self,
        field_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get recent corrections for a specific field.
        Used as hints during extraction.
        """
        index_path = os.path.join(self._store_path, "correction_index.json")
        if not os.path.exists(index_path):
            return []

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            return index.get(field_name, [])[:limit]
        except Exception:
            return []

    def get_company_corrections(
        self,
        company_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get all corrections for a company."""
        log_file = os.path.join(self._store_path, f"{company_id}_feedback.jsonl")
        if not os.path.exists(log_file):
            return []

        entries = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return list(reversed(entries))[:limit]

    def get_all_feedback(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all feedback across all companies."""
        all_entries = []

        for fname in os.listdir(self._store_path):
            if fname.endswith("_feedback.jsonl"):
                filepath = os.path.join(self._store_path, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                all_entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

        # Sort by timestamp descending
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_entries[:limit]

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get summary statistics about corrections."""
        all_feedback = self.get_all_feedback(limit=10000)

        if not all_feedback:
            return {"total_corrections": 0, "unique_fields": 0, "unique_companies": 0}

        fields = set()
        companies = set()
        for fb in all_feedback:
            fields.add(fb.get("field_name", ""))
            companies.add(fb.get("company_id", ""))

        return {
            "total_corrections": len(all_feedback),
            "unique_fields": len(fields),
            "unique_companies": len(companies),
            "most_corrected_fields": self._most_corrected_fields(all_feedback),
        }

    def _most_corrected_fields(self, feedback: List[Dict]) -> List[Dict]:
        """Find the most frequently corrected fields."""
        counts: Dict[str, int] = {}
        for fb in feedback:
            field = fb.get("field_name", "")
            counts[field] = counts.get(field, 0) + 1

        sorted_fields = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"field": f, "count": c} for f, c in sorted_fields[:10]]

    def _update_correction_index(
        self,
        field_name: str,
        original_value: Optional[str],
        corrected_value: str,
    ):
        """Update the fast-lookup correction index."""
        index_path = os.path.join(self._store_path, "correction_index.json")

        index: Dict[str, List] = {}
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = {}

        if field_name not in index:
            index[field_name] = []

        # Add correction (keep last 20 per field)
        index[field_name].insert(0, {
            "original": original_value,
            "corrected": corrected_value,
            "timestamp": datetime.utcnow().isoformat(),
        })
        index[field_name] = index[field_name][:20]

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)


# Module-level singleton
_feedback_store: Optional[FeedbackStore] = None


def get_feedback_store() -> FeedbackStore:
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore()
    return _feedback_store

