"""
Health & System Status API v2
==============================
Operational endpoints for monitoring, diagnostics, and administration.
"""

from typing import Dict, Any
from fastapi import APIRouter, Request
from pydantic import BaseModel
from config.settings import settings


router = APIRouter(prefix="/v2", tags=["System v2"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    components: Dict[str, str]


class SystemInfoResponse(BaseModel):
    platform: str
    version: str
    environment: str
    models: Dict[str, str]
    features: Dict[str, bool]
    thresholds: Dict[str, float]


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request):
    """Comprehensive health check for all platform components."""
    components = {}

    # Check Weaviate
    try:
        if hasattr(request.app.state, "weaviate_client"):
            request.app.state.weaviate_client.is_ready()
            components["weaviate"] = "healthy"
        else:
            components["weaviate"] = "not_initialized"
    except Exception:
        components["weaviate"] = "unhealthy"

    # Check Neo4j
    if settings.ENABLE_GRAPH:
        try:
            from entity.graph_engine import get_graph_engine
            graph = get_graph_engine()
            if graph._use_neo4j and graph._driver:
                graph._driver.verify_connectivity()
                components["neo4j"] = "healthy"
            else:
                components["neo4j"] = "fallback_json"
        except Exception:
            components["neo4j"] = "unhealthy"
    else:
        components["neo4j"] = "disabled"

    # Check LLM provider (Groq or Ollama)
    try:
        from rag_pipeline.llm_client import get_sync_client, get_provider_info
        provider_info = get_provider_info()
        components["llm_provider"] = provider_info["provider"]
        components["llm_status"] = "configured" if provider_info["has_api_key"] else "missing_key"
    except Exception:
        components["llm_status"] = "unhealthy"

    # Overall status
    unhealthy = [k for k, v in components.items() if v == "unhealthy"]
    overall = "degraded" if unhealthy else "healthy"

    return HealthResponse(
        status=f"Entity Intelligence Platform {overall} 🚀",
        version="2.0.0",
        environment=settings.ENVIRONMENT.value,
        components=components,
    )


@router.get("/info", response_model=SystemInfoResponse)
def system_info():
    """Get detailed system configuration (non-sensitive)."""
    return SystemInfoResponse(
        platform="Entity-Centric Document Intelligence Platform",
        version="2.0.0",
        environment=settings.ENVIRONMENT.value,
        models={
            "primary_llm": settings.PRIMARY_MODEL,
            "validator_llm": settings.VALIDATOR_MODEL,
            "classifier_llm": settings.CLASSIFIER_MODEL,
            "embedding": settings.EMBEDDING_MODEL,
            "layout": settings.LAYOUT_MODEL,
            "reranker": settings.RERANKER_MODEL,
        },
        features={
            "layout_extraction": settings.ENABLE_LAYOUT_EXTRACTION,
            "entity_graph": settings.ENABLE_GRAPH,
            "versioned_memory": settings.ENABLE_VERSIONED_MEMORY,
            "reranker": settings.ENABLE_RERANKER,
            "ocr_fallback": settings.ENABLE_OCR_FALLBACK,
            "audit_logging": settings.ENABLE_AUDIT_LOGGING,
            "api_key_auth": settings.ENABLE_API_KEY_AUTH,
        },
        thresholds={
            "autofill_confidence": settings.AUTOFILL_CONFIDENCE_THRESHOLD,
            "review_confidence": settings.REVIEW_CONFIDENCE_THRESHOLD,
            "layout_confidence": settings.LAYOUT_CONFIDENCE_THRESHOLD,
            "table_confidence": settings.TABLE_CONFIDENCE_THRESHOLD,
        },
    )


