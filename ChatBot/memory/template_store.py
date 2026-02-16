"""
Form Template Library
======================
Save and reuse form templates with pre-mapped field schemas
for instant autofill without re-detection.

A template captures:
  - Field names and positions detected in a form
  - Field types (text, checkbox, date, etc.)
  - Mapping to canonical entity fields
  - The form type (KYC, 499-A, W-9, etc.)

When the same form is uploaded again, fields are matched
from the template → skipping LLM-based detection entirely.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from config.settings import settings


class FormTemplate:
    """Represents a saved form template."""

    def __init__(
        self,
        template_id: str,
        name: str,
        form_type: str,
        fields: List[Dict[str, Any]],
        file_hash: Optional[str] = None,
        description: str = "",
        created_at: Optional[str] = None,
        usage_count: int = 0,
    ):
        self.template_id = template_id
        self.name = name
        self.form_type = form_type
        self.fields = fields
        self.file_hash = file_hash
        self.description = description
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.usage_count = usage_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "form_type": self.form_type,
            "fields": self.fields,
            "file_hash": self.file_hash,
            "description": self.description,
            "created_at": self.created_at,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormTemplate":
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            form_type=data.get("form_type", "unknown"),
            fields=data.get("fields", []),
            file_hash=data.get("file_hash"),
            description=data.get("description", ""),
            created_at=data.get("created_at"),
            usage_count=data.get("usage_count", 0),
        )


class TemplateStore:
    """
    Manages form templates for instant autofill.
    Templates are matched by file hash or structural similarity.
    """

    def __init__(self):
        self._store_path = os.path.join(settings.MEMORY_STORE_PATH, "templates.json")
        self._templates: Dict[str, FormTemplate] = {}
        self._load()

    def _load(self):
        """Load templates from disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tid, tdata in data.items():
                    self._templates[tid] = FormTemplate.from_dict(tdata)
            except Exception as e:
                print(f"[TEMPLATE] Failed to load templates: {e}")

    def _save(self):
        """Persist templates to disk."""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        data = {tid: t.to_dict() for tid, t in self._templates.items()}
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_template(
        self,
        name: str,
        form_type: str,
        fields: List[Dict[str, Any]],
        file_hash: Optional[str] = None,
        description: str = "",
    ) -> FormTemplate:
        """
        Save a new form template.

        Args:
            name: Human-readable template name (e.g. "DAZTEL KYC Form")
            form_type: Document type (kyc, tax, agreement, etc.)
            fields: List of detected fields with their metadata
            file_hash: SHA-256 hash for exact-match detection
            description: Optional description

        Returns:
            The saved FormTemplate
        """
        import uuid

        template_id = str(uuid.uuid4())[:8]
        template = FormTemplate(
            template_id=template_id,
            name=name,
            form_type=form_type,
            fields=fields,
            file_hash=file_hash,
            description=description,
        )

        self._templates[template_id] = template
        self._save()
        print(f"[TEMPLATE] Saved template '{name}' with {len(fields)} fields (id: {template_id})")
        return template

    def get_template(self, template_id: str) -> Optional[FormTemplate]:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def find_by_hash(self, file_hash: str) -> Optional[FormTemplate]:
        """
        Find a template matching the exact file hash.
        This means the same form was uploaded before.
        """
        for template in self._templates.values():
            if template.file_hash and template.file_hash == file_hash:
                template.usage_count += 1
                self._save()
                return template
        return None

    def find_by_name(self, name: str) -> List[FormTemplate]:
        """Search templates by name (fuzzy)."""
        name_lower = name.lower()
        results = []
        for template in self._templates.values():
            if name_lower in template.name.lower():
                results.append(template)
        return results

    def find_by_type(self, form_type: str) -> List[FormTemplate]:
        """Get all templates of a specific form type."""
        return [
            t for t in self._templates.values()
            if t.form_type.lower() == form_type.lower()
        ]

    def list_templates(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List all templates with summary info."""
        templates = sorted(
            self._templates.values(),
            key=lambda t: t.created_at or "",
            reverse=True,
        )
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "form_type": t.form_type,
                "field_count": len(t.fields),
                "description": t.description,
                "created_at": t.created_at,
                "usage_count": t.usage_count,
            }
            for t in templates[:limit]
        ]

    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        if template_id in self._templates:
            del self._templates[template_id]
            self._save()
            return True
        return False

    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        form_type: Optional[str] = None,
        fields: Optional[List[Dict]] = None,
        description: Optional[str] = None,
    ) -> Optional[FormTemplate]:
        """Update an existing template."""
        template = self._templates.get(template_id)
        if not template:
            return None

        if name is not None:
            template.name = name
        if form_type is not None:
            template.form_type = form_type
        if fields is not None:
            template.fields = fields
        if description is not None:
            template.description = description

        self._save()
        return template

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


# Module-level singleton
_template_store: Optional[TemplateStore] = None


def get_template_store() -> TemplateStore:
    global _template_store
    if _template_store is None:
        _template_store = TemplateStore()
    return _template_store

