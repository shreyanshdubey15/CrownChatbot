"""
Feedback Routes
================
/feedback, /feedback/stats
"""

from typing import Optional
from fastapi import APIRouter

from api.models import FeedbackRequest
from memory.feedback_store import get_feedback_store

router = APIRouter(tags=["Feedback"])


@router.post("/feedback", summary="Submit a user correction for a field value")
def submit_feedback(body: FeedbackRequest):
    """Log a user correction to improve future extractions."""
    store = get_feedback_store()
    feedback_id = store.log_correction(
        company_id=body.company_id,
        field_name=body.field_name,
        original_value=body.original_value,
        corrected_value=body.corrected_value,
        original_confidence=body.original_confidence,
        source_document=body.source_document,
        user_id=body.user_id,
        notes=body.notes,
    )
    return {"feedback_id": feedback_id, "message": "Correction logged successfully"}


@router.get("/feedback", summary="Get all feedback/corrections")
def get_feedback(company_id: Optional[str] = None, limit: int = 50):
    """Get user corrections, optionally filtered by company."""
    store = get_feedback_store()
    if company_id:
        corrections = store.get_company_corrections(company_id, limit=limit)
    else:
        corrections = store.get_all_feedback(limit=limit)
    return {"corrections": corrections, "total": len(corrections)}


@router.get("/feedback/stats", summary="Get feedback statistics")
def get_feedback_stats():
    """Get summary statistics about user corrections."""
    store = get_feedback_store()
    return store.get_feedback_stats()


