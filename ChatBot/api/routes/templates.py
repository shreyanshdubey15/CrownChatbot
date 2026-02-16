"""
Template Routes
================
/templates CRUD
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from api.models import TemplateCreateRequest, TemplateUpdateRequest
from memory.template_store import get_template_store

router = APIRouter(tags=["Templates"])


@router.post("/templates", summary="Save a new form template")
def create_template(body: TemplateCreateRequest):
    """Save a form template for reuse across future autofills."""
    store = get_template_store()
    template = store.save_template(
        name=body.name,
        form_type=body.form_type,
        fields=body.fields,
        file_hash=body.file_hash,
        description=body.description,
    )
    return template.to_dict()


@router.get("/templates", summary="List all form templates")
def list_templates(form_type: Optional[str] = None, limit: int = 50):
    """List saved form templates with optional type filter."""
    store = get_template_store()
    if form_type:
        templates = [
            {
                "template_id": t.template_id,
                "name": t.name,
                "form_type": t.form_type,
                "field_count": len(t.fields),
                "description": t.description,
                "created_at": t.created_at,
                "usage_count": t.usage_count,
            }
            for t in store.find_by_type(form_type)
        ]
    else:
        templates = store.list_templates(limit=limit)
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{template_id}", summary="Get a specific template")
def get_template(template_id: str):
    """Get full template details including field schema."""
    store = get_template_store()
    template = store.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    return template.to_dict()


@router.put("/templates/{template_id}", summary="Update a template")
def update_template(template_id: str, body: TemplateUpdateRequest):
    """Update an existing form template."""
    store = get_template_store()
    template = store.update_template(
        template_id=template_id,
        name=body.name,
        form_type=body.form_type,
        fields=body.fields,
        description=body.description,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    return template.to_dict()


@router.delete("/templates/{template_id}", summary="Delete a template")
def delete_template(template_id: str):
    """Delete a form template."""
    store = get_template_store()
    if not store.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found.")
    return {"message": "Template deleted"}


