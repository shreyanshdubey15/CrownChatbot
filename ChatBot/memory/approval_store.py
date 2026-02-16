"""
Approval Workflow Store
========================
Multi-step approval for high-stakes autofills.

Workflow:
  1. Analyst fills form → creates approval request (status: pending)
  2. Manager reviews → approves/rejects (status: approved/rejected)
  3. Compliance verifies → final sign-off (status: final_approved)

Each step is logged with user, timestamp, and comments.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from config.settings import settings


class ApprovalRequest:
    """Single approval workflow request."""

    def __init__(
        self,
        request_id: str,
        document_name: str,
        company_id: Optional[str],
        fields: List[Dict[str, Any]],
        file_id: Optional[str] = None,
        file_ext: Optional[str] = None,
        status: str = "pending",
        created_by: str = "system",
        created_at: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.request_id = request_id
        self.document_name = document_name
        self.company_id = company_id
        self.fields = fields
        self.file_id = file_id
        self.file_ext = file_ext
        self.status = status
        self.created_by = created_by
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.steps = steps or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "document_name": self.document_name,
            "company_id": self.company_id,
            "fields": self.fields,
            "file_id": self.file_id,
            "file_ext": self.file_ext,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "steps": self.steps,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRequest":
        return cls(**data)


class ApprovalStore:
    """
    Manages approval workflow requests.
    Each request goes through: pending → reviewed → approved/rejected → final_approved.
    """

    VALID_STATUSES = {"pending", "reviewed", "approved", "rejected", "final_approved", "cancelled"}

    def __init__(self):
        self._store_path = os.path.join(settings.MEMORY_STORE_PATH, "approvals.json")
        self._requests: Dict[str, ApprovalRequest] = {}
        self._load()

    def _load(self):
        """Load from disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for rid, rdata in data.items():
                    self._requests[rid] = ApprovalRequest.from_dict(rdata)
            except Exception as e:
                print(f"[APPROVAL] Failed to load approvals: {e}")

    def _save(self):
        """Persist to disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        data = {rid: r.to_dict() for rid, r in self._requests.items()}
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def create_request(
        self,
        document_name: str,
        company_id: Optional[str],
        fields: List[Dict[str, Any]],
        file_id: Optional[str] = None,
        file_ext: Optional[str] = None,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Create a new approval request."""
        request_id = str(uuid.uuid4())[:12]
        request = ApprovalRequest(
            request_id=request_id,
            document_name=document_name,
            company_id=company_id,
            fields=fields,
            file_id=file_id,
            file_ext=file_ext,
            created_by=created_by,
            metadata=metadata or {},
        )

        self._requests[request_id] = request
        self._save()
        return request

    def add_step(
        self,
        request_id: str,
        action: str,
        user_id: str = "reviewer",
        comment: Optional[str] = None,
        field_corrections: Optional[Dict[str, str]] = None,
    ) -> Optional[ApprovalRequest]:
        """
        Add an approval step.

        action: "approve", "reject", "request_changes", "final_approve"
        """
        request = self._requests.get(request_id)
        if not request:
            return None

        step = {
            "step_id": str(uuid.uuid4())[:8],
            "action": action,
            "user_id": user_id,
            "comment": comment,
            "field_corrections": field_corrections,
            "timestamp": datetime.utcnow().isoformat(),
        }

        request.steps.append(step)

        # Update status based on action
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "request_changes": "pending",
            "final_approve": "final_approved",
            "cancel": "cancelled",
        }
        new_status = status_map.get(action, request.status)
        request.status = new_status

        # Apply field corrections if any
        if field_corrections:
            for field in request.fields:
                fname = field.get("field", "")
                if fname in field_corrections:
                    field["value"] = field_corrections[fname]
                    field["corrected_by"] = user_id

        self._save()
        return request

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a request by ID."""
        return self._requests.get(request_id)

    def list_requests(
        self,
        status: Optional[str] = None,
        company_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List approval requests with optional filters."""
        results = []
        for request in sorted(
            self._requests.values(),
            key=lambda r: r.created_at or "",
            reverse=True,
        ):
            if status and request.status != status:
                continue
            if company_id and request.company_id != company_id:
                continue
            results.append({
                "request_id": request.request_id,
                "document_name": request.document_name,
                "company_id": request.company_id,
                "status": request.status,
                "field_count": len(request.fields),
                "filled_count": sum(1 for f in request.fields if f.get("value")),
                "step_count": len(request.steps),
                "created_by": request.created_by,
                "created_at": request.created_at,
            })
            if len(results) >= limit:
                break
        return results

    def get_pending_count(self) -> int:
        """Get count of pending approval requests."""
        return sum(1 for r in self._requests.values() if r.status == "pending")

    def delete_request(self, request_id: str) -> bool:
        """Delete a request."""
        if request_id in self._requests:
            del self._requests[request_id]
            self._save()
            return True
        return False


# Module-level singleton
_approval_store: Optional[ApprovalStore] = None


def get_approval_store() -> ApprovalStore:
    global _approval_store
    if _approval_store is None:
        _approval_store = ApprovalStore()
    return _approval_store

