"""
Approval Workflow Routes
=========================
/approvals CRUD + step management
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from api.models import ApprovalCreateRequest, ApprovalStepRequest
from memory.approval_store import get_approval_store

router = APIRouter(tags=["Approvals"])


@router.post("/approvals", summary="Create a new approval request")
def create_approval(body: ApprovalCreateRequest):
    """Create a new approval request for high-stakes autofills."""
    store = get_approval_store()
    request = store.create_request(
        document_name=body.document_name,
        company_id=body.company_id,
        fields=body.fields,
        file_id=body.file_id,
        file_ext=body.file_ext,
        created_by=body.created_by,
    )
    return request.to_dict()


@router.get("/approvals", summary="List approval requests")
def list_approvals(
    approval_status: Optional[str] = None,
    company_id: Optional[str] = None,
    limit: int = 50,
):
    """List approval requests with optional status/company filter."""
    store = get_approval_store()
    requests = store.list_requests(
        status=approval_status,
        company_id=company_id,
        limit=limit,
    )
    return {"requests": requests, "total": len(requests), "pending": store.get_pending_count()}


@router.get("/approvals/{request_id}", summary="Get approval request details")
def get_approval(request_id: str):
    """Get full details of an approval request including all steps."""
    store = get_approval_store()
    req = store.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return req.to_dict()


@router.post("/approvals/{request_id}/step", summary="Add an approval step")
def add_approval_step(request_id: str, body: ApprovalStepRequest):
    """Add an approval/rejection step to a request."""
    store = get_approval_store()
    req = store.add_step(
        request_id=request_id,
        action=body.action,
        user_id=body.user_id,
        comment=body.comment,
        field_corrections=body.field_corrections,
    )
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return req.to_dict()


@router.delete("/approvals/{request_id}", summary="Delete an approval request")
def delete_approval(request_id: str):
    """Delete an approval request."""
    store = get_approval_store()
    if not store.delete_request(request_id):
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return {"message": "Approval request deleted"}


