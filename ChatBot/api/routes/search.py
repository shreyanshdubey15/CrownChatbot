"""
Search Routes
==============
/search, /entity-search
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Request

from api.models import SearchRequest

router = APIRouter(tags=["Search"])


@router.post("/search", summary="Semantic search across all documents")
def semantic_search(body: SearchRequest, request: Request):
    """Hybrid search (BM25 + vector) across all indexed documents."""
    try:
        from rag_pipeline.retriever import Retriever
        retriever = Retriever(client=request.app.state.weaviate_client)
        results = retriever.search(body.query, top_k=body.top_k)

        return {
            "query": body.query,
            "results": results,
            "total": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.get("/entity-search", summary="Search across all company entities")
def cross_entity_search(
    request: Request,
    q: str = "",
    field_name: Optional[str] = None,
    field_value: Optional[str] = None,
    limit: int = 20,
):
    """Cross-company entity search by query string, or by specific field name/value."""
    try:
        try:
            from entity.graph_engine import get_graph_engine
            graph = get_graph_engine()

            if q:
                companies = graph.search_companies(q, limit=limit)
            elif field_name and field_value:
                all_ids = graph.list_companies(limit=500)
                companies = []
                for cid in all_ids:
                    profile = graph.get_company(cid)
                    if profile:
                        val = profile.get_field_value(field_name)
                        if val and field_value.lower() in val.lower():
                            companies.append(profile)
                    if len(companies) >= limit:
                        break
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Provide either 'q' or 'field_name' + 'field_value'",
                )

            results = []
            for p in companies:
                results.append({
                    "company_id": getattr(p, "company_id", ""),
                    "company_name": p.get_field_value("company_name") if hasattr(p, "get_field_value") else "",
                    "ein": p.get_field_value("ein") if hasattr(p, "get_field_value") else "",
                    "fcc_499_id": p.get_field_value("fcc_499_id") if hasattr(p, "get_field_value") else "",
                    "entity_type": p.get_field_value("entity_type") if hasattr(p, "get_field_value") else "",
                    "address": p.get_field_value("address") if hasattr(p, "get_field_value") else "",
                    "phone": p.get_field_value("phone") if hasattr(p, "get_field_value") else "",
                    "email": p.get_field_value("email") if hasattr(p, "get_field_value") else "",
                    "field_count": len(getattr(p, "fields", [])),
                    "document_count": len(getattr(p, "linked_documents", [])),
                })

            return {"query": q or f"{field_name}={field_value}", "results": results, "total": len(results)}

        except ImportError:
            from rag_pipeline.autofill_engine import _load_memory
            memory = _load_memory()

            results = []
            search_term = (q or field_value or "").lower()

            for company_id, profile in memory.items():
                if search_term:
                    match = False
                    for k, v in profile.items():
                        val_str = str(v.get("value", "")) if isinstance(v, dict) else str(v)
                        if search_term in val_str.lower() or search_term in company_id.lower():
                            match = True
                            break
                    if not match:
                        continue

                entry = {"company_id": company_id}
                for k, v in profile.items():
                    val = v.get("value", "") if isinstance(v, dict) else str(v)
                    entry[k] = val
                entry["field_count"] = len(profile)
                entry["document_count"] = 0
                results.append(entry)

                if len(results) >= limit:
                    break

            return {"query": q or f"{field_name}={field_value}", "results": results, "total": len(results)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Entity search failed: {e}")


