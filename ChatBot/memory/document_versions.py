"""
Document Versioning Store
===========================
Tracks multiple versions of the same document.
Supports duplicate detection using SHA-256 file hashes.

Use cases:
  - Re-uploaded signed contract vs unsigned
  - Updated KYC form
  - Amended agreement

Each document has:
  - version history
  - file hashes for dedup
  - comparison metadata
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from config.settings import settings


class DocumentVersion:
    """A single version of a document."""

    def __init__(
        self,
        version_id: str,
        filename: str,
        file_hash: str,
        file_size: int,
        upload_timestamp: Optional[str] = None,
        uploaded_by: str = "system",
        file_path: Optional[str] = None,
        notes: str = "",
    ):
        self.version_id = version_id
        self.filename = filename
        self.file_hash = file_hash
        self.file_size = file_size
        self.upload_timestamp = upload_timestamp or datetime.utcnow().isoformat()
        self.uploaded_by = uploaded_by
        self.file_path = file_path
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "upload_timestamp": self.upload_timestamp,
            "uploaded_by": self.uploaded_by,
            "file_path": self.file_path,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentVersion":
        return cls(**data)


class DocumentRecord:
    """A document with its version history."""

    def __init__(
        self,
        document_id: str,
        original_filename: str,
        versions: Optional[List[DocumentVersion]] = None,
        document_type: str = "unknown",
        company_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        self.document_id = document_id
        self.original_filename = original_filename
        self.versions = versions or []
        self.document_type = document_type
        self.company_id = company_id
        self.tags = tags or []

    @property
    def latest_version(self) -> Optional[DocumentVersion]:
        return self.versions[-1] if self.versions else None

    @property
    def version_count(self) -> int:
        return len(self.versions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "versions": [v.to_dict() for v in self.versions],
            "document_type": self.document_type,
            "company_id": self.company_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentRecord":
        versions = [DocumentVersion.from_dict(v) for v in data.get("versions", [])]
        return cls(
            document_id=data["document_id"],
            original_filename=data["original_filename"],
            versions=versions,
            document_type=data.get("document_type", "unknown"),
            company_id=data.get("company_id"),
            tags=data.get("tags", []),
        )


class DocumentVersionStore:
    """
    Manages document versioning and duplicate detection.
    """

    def __init__(self):
        self._store_path = os.path.join(settings.MEMORY_STORE_PATH, "document_versions.json")
        self._records: Dict[str, DocumentRecord] = {}
        self._hash_index: Dict[str, str] = {}  # file_hash → document_id
        self._load()

    def _load(self):
        """Load from disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for did, rdata in data.get("records", {}).items():
                    record = DocumentRecord.from_dict(rdata)
                    self._records[did] = record
                    for v in record.versions:
                        self._hash_index[v.file_hash] = did
            except Exception as e:
                print(f"[DOC_VERSION] Failed to load: {e}")

    def _save(self):
        """Persist to disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        data = {
            "records": {did: r.to_dict() for did, r in self._records.items()},
        }
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def compute_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def check_duplicate(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """
        Check if a file with this hash already exists.

        Returns:
            Dict with document_id and version info if duplicate, else None
        """
        doc_id = self._hash_index.get(file_hash)
        if doc_id and doc_id in self._records:
            record = self._records[doc_id]
            for v in record.versions:
                if v.file_hash == file_hash:
                    return {
                        "is_duplicate": True,
                        "document_id": doc_id,
                        "filename": record.original_filename,
                        "version_id": v.version_id,
                        "uploaded_at": v.upload_timestamp,
                        "message": f"Exact duplicate of '{record.original_filename}' (version {v.version_id})",
                    }
        return None

    def add_document(
        self,
        filename: str,
        file_path: str,
        file_hash: Optional[str] = None,
        document_type: str = "unknown",
        company_id: Optional[str] = None,
        uploaded_by: str = "system",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Add a document (new or new version of existing).

        Returns:
            {document_id, version_id, is_new, version_number}
        """
        import uuid

        if not file_hash:
            file_hash = self.compute_hash(file_path)

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        # Check for exact duplicate
        dup = self.check_duplicate(file_hash)
        if dup:
            return {
                "document_id": dup["document_id"],
                "version_id": dup["version_id"],
                "is_new": False,
                "is_duplicate": True,
                "version_number": 0,
                "message": dup["message"],
            }

        # Check if this is a new version of an existing document (by filename similarity)
        existing_record = self._find_by_filename(filename)

        version_id = str(uuid.uuid4())[:8]
        version = DocumentVersion(
            version_id=version_id,
            filename=filename,
            file_hash=file_hash,
            file_size=file_size,
            uploaded_by=uploaded_by,
            file_path=file_path,
            notes=notes,
        )

        if existing_record:
            # Add as new version
            existing_record.versions.append(version)
            self._hash_index[file_hash] = existing_record.document_id
            self._save()
            return {
                "document_id": existing_record.document_id,
                "version_id": version_id,
                "is_new": False,
                "is_duplicate": False,
                "version_number": len(existing_record.versions),
                "message": f"New version ({len(existing_record.versions)}) of '{existing_record.original_filename}'",
            }

        # New document
        document_id = str(uuid.uuid4())
        record = DocumentRecord(
            document_id=document_id,
            original_filename=filename,
            versions=[version],
            document_type=document_type,
            company_id=company_id,
        )
        self._records[document_id] = record
        self._hash_index[file_hash] = document_id
        self._save()

        return {
            "document_id": document_id,
            "version_id": version_id,
            "is_new": True,
            "is_duplicate": False,
            "version_number": 1,
            "message": f"New document '{filename}' registered",
        }

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document record with all versions."""
        record = self._records.get(document_id)
        if record:
            return record.to_dict()
        return None

    def get_versions(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all versions of a document."""
        record = self._records.get(document_id)
        if record:
            return [v.to_dict() for v in record.versions]
        return []

    def list_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all documents with summary info."""
        results = []
        for record in sorted(
            self._records.values(),
            key=lambda r: r.latest_version.upload_timestamp if r.latest_version else "",
            reverse=True,
        ):
            latest = record.latest_version
            results.append({
                "document_id": record.document_id,
                "filename": record.original_filename,
                "document_type": record.document_type,
                "company_id": record.company_id,
                "version_count": record.version_count,
                "latest_version": latest.to_dict() if latest else None,
                "tags": record.tags,
            })
            if len(results) >= limit:
                break
        return results

    def _find_by_filename(self, filename: str) -> Optional[DocumentRecord]:
        """Find a document record by similar filename."""
        # Strip common suffixes like " Signed", " (1)", " v2"
        import re
        base = re.sub(r"\s*(signed|v\d+|\(\d+\)|copy|final|draft)\s*", "", filename, flags=re.IGNORECASE)
        base = base.rsplit(".", 1)[0].strip().lower()

        for record in self._records.values():
            existing_base = re.sub(
                r"\s*(signed|v\d+|\(\d+\)|copy|final|draft)\s*",
                "",
                record.original_filename,
                flags=re.IGNORECASE,
            )
            existing_base = existing_base.rsplit(".", 1)[0].strip().lower()

            if base == existing_base:
                return record

        return None


# Module-level singleton
_version_store: Optional[DocumentVersionStore] = None


def get_document_version_store() -> DocumentVersionStore:
    global _version_store
    if _version_store is None:
        _version_store = DocumentVersionStore()
    return _version_store


def reset_document_version_store():
    """Reset the singleton — clears in-memory cache AND on-disk data."""
    global _version_store
    store = get_document_version_store()
    store._records.clear()
    store._hash_index.clear()
    store._save()
    _version_store = None

