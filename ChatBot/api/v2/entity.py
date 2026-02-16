"""
Entity / Company Profile API v2
=================================
Endpoints for the Master Company Profile Engine.
Manages company entities, version history, and audit trails.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


router = APIRouter(prefix="/v2/entity", tags=["Entity Graph v2"])


# ── Response Models ──────────────────────────────────────────

class CompanyProfileResponse(BaseModel):
    company_id: str
    fields: Dict[str, Any]
    linked_documents: List[str]
    conflicts: Dict[str, Any]
    needs_review: Dict[str, Any]
    is_verified: bool
    created_at: str
    updated_at: str


class FieldHistoryEntry(BaseModel):
    version: int
    value: str
    confidence: float
    source_document: str
    source_page: Optional[int]
    extraction_method: str
    extracted_at: str
    change_reason: Optional[str]
    is_active: bool


class FieldHistoryResponse(BaseModel):
    company_id: str
    field_name: str
    history: List[FieldHistoryEntry]


class CompanyListResponse(BaseModel):
    companies: List[str]
    total: int


class RelationshipResponse(BaseModel):
    source_company_id: str
    target_company_id: str
    relationship_type: str
    confidence: float


class DocumentLinkResponse(BaseModel):
    document_id: str
    filename: Optional[str] = None
    document_type: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────

@router.get(
    "/companies",
    response_model=CompanyListResponse,
    summary="List all company entities",
)
def list_companies(
    limit: int = Query(50, ge=1, le=200),
):
    """List all company IDs in the entity graph."""
    from entity.graph_engine import get_graph_engine

    graph = get_graph_engine()
    companies = graph.list_companies(limit=limit)
    return CompanyListResponse(companies=companies, total=len(companies))


@router.get(
    "/company/{company_id}",
    response_model=CompanyProfileResponse,
    summary="Get Master Company Profile",
)
def get_company_profile(company_id: str):
    """
    Retrieve the full Master Company Profile with all field versions,
    conflicts, and review flags.
    """
    from entity.graph_engine import get_graph_engine

    graph = get_graph_engine()
    profile = graph.get_company(company_id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found.")

    # Serialize fields with current values
    fields_out = {}
    for name, field in profile.fields.items():
        fields_out[name] = {
            "value": field.current_value,
            "confidence": field.current_confidence,
            "source": field.current_source,
            "version_count": len(field.versions),
            "needs_review": field.needs_review,
            "conflict": field.conflict_flag,
        }

    conflicts_out = {}
    for name, field in profile.get_conflicts().items():
        conflicts_out[name] = {
            "current_value": field.current_value,
            "conflicting_versions": [
                {"value": v.value, "source": v.source_document, "confidence": v.confidence}
                for v in field.versions if not v.is_active
            ],
        }

    review_out = {}
    for name, field in profile.get_needs_review().items():
        review_out[name] = {
            "value": field.current_value,
            "confidence": field.current_confidence,
        }

    return CompanyProfileResponse(
        company_id=profile.company_id,
        fields=fields_out,
        linked_documents=profile.linked_documents,
        conflicts=conflicts_out,
        needs_review=review_out,
        is_verified=profile.is_verified,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


@router.get(
    "/company/{company_id}/field/{field_name}/history",
    response_model=FieldHistoryResponse,
    summary="Get version history for a specific field",
)
def get_field_history(company_id: str, field_name: str):
    """
    Full version history for a single field.
    Required for compliance audit — shows every value change with provenance.
    """
    from entity.profile_builder import ProfileBuilder
    from entity.graph_engine import get_graph_engine
    from memory.versioned_store import get_versioned_store

    graph = get_graph_engine()
    memory = get_versioned_store()
    builder = ProfileBuilder(graph_engine=graph, versioned_memory=memory)

    history = builder.get_field_history(company_id, field_name)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No history found for field '{field_name}' on company '{company_id}'."
        )

    return FieldHistoryResponse(
        company_id=company_id,
        field_name=field_name,
        history=[FieldHistoryEntry(**h) for h in history],
    )


@router.get(
    "/company/{company_id}/documents",
    response_model=List[DocumentLinkResponse],
    summary="Get all documents linked to a company",
)
def get_company_documents(company_id: str):
    """Get all documents that contributed to this company's profile."""
    from entity.graph_engine import get_graph_engine

    graph = get_graph_engine()
    docs = graph.get_company_documents(company_id)
    return [DocumentLinkResponse(**d) for d in docs]


@router.get(
    "/company/{company_id}/relationships",
    response_model=List[RelationshipResponse],
    summary="Get entity relationships for a company",
)
def get_company_relationships(
    company_id: str,
    relationship_type: Optional[str] = Query(None),
):
    """Get all relationships (carrier partnerships, subsidiaries, etc.)."""
    from entity.graph_engine import get_graph_engine

    graph = get_graph_engine()
    rels = graph.get_relationships(company_id, relationship_type)
    return [
        RelationshipResponse(
            source_company_id=r.source_company_id,
            target_company_id=r.target_company_id,
            relationship_type=r.relationship_type,
            confidence=r.confidence,
        )
        for r in rels
    ]


@router.get(
    "/search",
    summary="Search companies by name, EIN, or FCC ID",
)
def search_companies(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
):
    """Full-text search across company entities."""
    from entity.graph_engine import get_graph_engine

    graph = get_graph_engine()
    results = graph.search_companies(q, limit)

    return {
        "query": q,
        "total": len(results),
        "companies": [
            {
                "company_id": p.company_id,
                "company_name": p.get_field_value("company_name"),
                "ein": p.get_field_value("ein"),
                "fcc_499_id": p.get_field_value("fcc_499_id"),
            }
            for p in results
        ],
    }


@router.get(
    "/company/{company_id}/audit",
    summary="Get audit event history for a company",
)
def get_audit_history(
    company_id: str,
    field_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Retrieve the full audit event log for a company.
    Optionally filter by field name.
    """
    from memory.versioned_store import get_versioned_store

    store = get_versioned_store()
    events = store.get_event_history(
        company_id=company_id,
        field_name=field_name,
        limit=limit,
    )

    return {
        "company_id": company_id,
        "total_events": len(events),
        "events": events,
    }


@router.get(
    "/company/{company_id}/snapshots",
    summary="List profile snapshots for rollback",
)
def list_snapshots(company_id: str):
    """List all point-in-time profile snapshots."""
    from memory.versioned_store import get_versioned_store

    store = get_versioned_store()
    snapshots = store.list_snapshots(company_id)
    return {"company_id": company_id, "snapshots": snapshots}


@router.post(
    "/company/{company_id}/rollback",
    summary="Rollback company profile to a previous snapshot",
)
def rollback_profile(company_id: str, snapshot_filename: str = Query(...)):
    """
    Rollback a company profile to a previous point-in-time.
    The rollback is logged as an audit event.
    """
    from memory.versioned_store import get_versioned_store
    from entity.graph_engine import get_graph_engine

    store = get_versioned_store()
    profile = store.rollback_to_snapshot(company_id, snapshot_filename)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_filename}' not found.")

    # Re-save to graph
    graph = get_graph_engine()
    graph.upsert_company(profile)

    return {
        "company_id": company_id,
        "rolled_back_to": snapshot_filename,
        "status": "success",
    }






