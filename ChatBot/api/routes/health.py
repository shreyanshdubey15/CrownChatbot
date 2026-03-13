"""
Health & LLM Provider Routes
==============================
/health, /llm-provider, /ui
"""

import os
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse

from api.models import HealthResponse
from config.constants import FRONTEND_DIR

router = APIRouter()


@router.get("/", tags=["Frontend"])
@router.get("/dashboard", tags=["Frontend"])
@router.get("/ui", tags=["Frontend"])
def serve_frontend():
    """Serve the RAG Chatbot frontend."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@router.get("/health", response_model=HealthResponse, tags=["Service"])
def health_check():
    """Check if the AI Chatbot is alive and healthy."""
    return HealthResponse(status="AI chatbot running 🚀")


@router.get("/llm-provider", tags=["Service"], summary="Get active LLM provider info")
def get_llm_provider():
    """Return details about the currently active LLM backend (Groq or Ollama)."""
    from rag_pipeline.llm_client import get_provider_info
    return get_provider_info()


@router.post("/llm-provider", tags=["Service"], summary="Switch LLM provider at runtime")
def set_llm_provider(request: Request, provider: str = Form(..., description="'groq' or 'ollama'")):
    """Hot-switch between Groq and Ollama without restarting the server."""
    provider = provider.strip().lower()
    if provider not in ("groq", "ollama"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{provider}'. Must be 'groq' or 'ollama'."
        )
    os.environ["LLM_PROVIDER"] = provider

    from rag_pipeline.llm_client import get_sync_client, get_provider_info
    request.app.state.bot.client = get_sync_client()

    return {
        "message": f"LLM provider switched to '{provider}'",
        **get_provider_info(),
    }


