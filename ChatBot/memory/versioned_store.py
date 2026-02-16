"""
Versioned Memory Store — Append-Only Event Store
==================================================
Company data evolves over time. This store NEVER overwrites.
Every change is an event that can be replayed.

Design: Temporal database pattern / append-only event store.

Example version history:
  EIN:
    v1 → "12-3456789" → Source: KYC_2023.pdf, confidence: 0.95
    v2 → "12-3456790" → Source: TaxDoc_2025.pdf, confidence: 0.98

Banks REQUIRE this behavior for regulatory compliance.

Storage: JSON-based event log (production: PostgreSQL + event sourcing)
"""

import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.schemas.company import CompanyProfile
from core.schemas.enums import AuditAction
from config.settings import settings


class VersionEvent(dict):
    """Single event in the version history."""
    pass


class VersionedMemoryStore:
    """
    Append-only versioned memory store.
    Every profile change is logged as an event.
    Supports full rollback and audit replay.
    """

    def __init__(self):
        self._event_log_path = settings.EVENT_LOG_PATH
        self._snapshot_path = os.path.join(settings.MEMORY_STORE_PATH, "snapshots")
        os.makedirs(self._event_log_path, exist_ok=True)
        os.makedirs(self._snapshot_path, exist_ok=True)

    # ── Event Logging ────────────────────────────────────────

    def log_event(
        self,
        company_id: str,
        action: AuditAction,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        confidence: Optional[float] = None,
        source_document: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Append an event to the company's event log.
        Returns event_id.
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "company_id": company_id,
            "action": action.value,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "confidence": confidence,
            "source_document": source_document,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        # Append to company-specific event log
        log_file = os.path.join(self._event_log_path, f"{company_id}_events.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

        return event_id

    def get_event_history(
        self,
        company_id: str,
        field_name: Optional[str] = None,
        action: Optional[AuditAction] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Replay event history for a company.
        Optionally filter by field_name or action type.
        """
        log_file = os.path.join(self._event_log_path, f"{company_id}_events.jsonl")
        if not os.path.exists(log_file):
            return []

        events = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if field_name and event.get("field_name") != field_name:
                        continue
                    if action and event.get("action") != action.value:
                        continue
                    events.append(event)
                except json.JSONDecodeError:
                    continue

        # Return most recent first, limited
        return list(reversed(events))[:limit]

    # ── Profile Snapshots ────────────────────────────────────

    def save_profile_snapshot(
        self,
        company_id: str,
        profile: CompanyProfile,
    ) -> str:
        """
        Save a point-in-time snapshot of the company profile.
        Used for rollback and audit comparison.
        """
        snapshot_id = str(uuid.uuid4())
        snapshot = {
            "snapshot_id": snapshot_id,
            "company_id": company_id,
            "timestamp": datetime.utcnow().isoformat(),
            "profile": profile.model_dump(mode="json"),
        }

        # Save to company-specific snapshot directory
        company_dir = os.path.join(self._snapshot_path, company_id)
        os.makedirs(company_dir, exist_ok=True)

        snapshot_file = os.path.join(
            company_dir,
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{snapshot_id[:8]}.json"
        )

        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)

        # Log the snapshot event
        self.log_event(
            company_id=company_id,
            action=AuditAction.PROFILE_BUILT,
            metadata={"snapshot_id": snapshot_id},
        )

        return snapshot_id

    def get_latest_snapshot(
        self,
        company_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent profile snapshot."""
        company_dir = os.path.join(self._snapshot_path, company_id)
        if not os.path.exists(company_dir):
            return None

        snapshots = sorted(os.listdir(company_dir), reverse=True)
        if not snapshots:
            return None

        snapshot_file = os.path.join(company_dir, snapshots[0])
        with open(snapshot_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_snapshots(
        self,
        company_id: str,
    ) -> List[Dict[str, str]]:
        """List all snapshots for a company (metadata only)."""
        company_dir = os.path.join(self._snapshot_path, company_id)
        if not os.path.exists(company_dir):
            return []

        snapshots = []
        for fname in sorted(os.listdir(company_dir), reverse=True):
            snapshots.append({
                "filename": fname,
                "path": os.path.join(company_dir, fname),
            })
        return snapshots

    def rollback_to_snapshot(
        self,
        company_id: str,
        snapshot_filename: str,
    ) -> Optional[CompanyProfile]:
        """
        Rollback a company profile to a previous snapshot.
        The rollback itself is logged as an event.
        """
        company_dir = os.path.join(self._snapshot_path, company_id)
        snapshot_path = os.path.join(company_dir, snapshot_filename)

        if not os.path.exists(snapshot_path):
            return None

        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        profile = CompanyProfile.model_validate(snapshot["profile"])

        self.log_event(
            company_id=company_id,
            action=AuditAction.ENTITY_UPDATED,
            metadata={
                "rollback_to": snapshot_filename,
                "rollback_snapshot_id": snapshot.get("snapshot_id"),
            },
        )

        return profile


# ── Audit Trail Writer ───────────────────────────────────────

class AuditTrailWriter:
    """
    Writes immutable audit trail entries for compliance.
    Separate from event log — this is for regulatory auditors.
    """

    def __init__(self):
        self._audit_path = settings.AUDIT_TRAIL_PATH
        os.makedirs(self._audit_path, exist_ok=True)

    def log(
        self,
        action: AuditAction,
        entity_type: str,            # "company" | "document" | "field"
        entity_id: str,
        details: Dict[str, Any],
        user_id: str = "system",
    ) -> str:
        """Write an immutable audit entry."""
        audit_id = str(uuid.uuid4())
        entry = {
            "audit_id": audit_id,
            "action": action.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Append to daily audit log
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = os.path.join(self._audit_path, f"audit_{date_str}.jsonl")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        return audit_id


# Module-level singletons
_versioned_store: Optional[VersionedMemoryStore] = None
_audit_writer: Optional[AuditTrailWriter] = None


def get_versioned_store() -> VersionedMemoryStore:
    global _versioned_store
    if _versioned_store is None:
        _versioned_store = VersionedMemoryStore()
    return _versioned_store


def get_audit_writer() -> AuditTrailWriter:
    global _audit_writer
    if _audit_writer is None:
        _audit_writer = AuditTrailWriter()
    return _audit_writer






