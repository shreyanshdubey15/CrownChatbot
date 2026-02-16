"""
RAG Chatbot — Application Entry Point
=======================================
Thin orchestrator: creates the FastAPI app, wires up lifespan,
includes all route modules, and mounts static files.

All route handlers live in api/routes/*.py
All Pydantic models live in api/models.py
All form-filling logic lives in utils/form_filler.py
"""

import os
import sys

# ── HEIF shim (must run before any unstructured import) ──────
import pillow_heif
sys.modules["pi_heif"] = pillow_heif

from contextlib import asynccontextmanager

import weaviate
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rag_pipeline.chain import RAGChain
from rag_pipeline.embeddings import EmbeddingModel
from rag_pipeline.autofill_engine import AutofillEngine
from config.constants import UPLOAD_DIR, AUTOFILL_TEMP_DIR, FRONTEND_DIR

# Ensure data directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUTOFILL_TEMP_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────
#  LIFESPAN — startup / shutdown
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    print("[STARTUP] Initializing RAG resources...")
    from pillow_heif import register_heif_opener
    register_heif_opener()

    EmbeddingModel()  # Load singleton

    # Shared Weaviate Client
    app.state.weaviate_client = weaviate.connect_to_local()

    # Initialize shared bot with shared client
    app.state.bot = RAGChain(client=app.state.weaviate_client)

    # Initialize Autofill Engine (independent from chatbot)
    app.state.autofill_engine = AutofillEngine(weaviate_client=app.state.weaviate_client)

    yield

    # ── Shutdown ─────────────────────────────────────────────
    print("[SHUTDOWN] Shutting down...")
    if hasattr(app.state, "weaviate_client"):
        app.state.weaviate_client.close()


# ─────────────────────────────────────────────────────────────
#  APP FACTORY
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="RAG Chatbot API",
    description="Production-ready RAG system with PDF, DOCX, and DOC support",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─────────────────────────────────────────────────────────────
#  REGISTER ROUTE MODULES  (v1 — flat endpoints)
# ─────────────────────────────────────────────────────────────

from api.routes.health import router as health_router
from api.routes.rag import router as rag_router
from api.routes.ingestion import router as ingestion_router
from api.routes.autofill import router as autofill_router
from api.routes.documents import router as documents_router
from api.routes.extraction import router as extraction_router
from api.routes.feedback import router as feedback_router
from api.routes.templates import router as templates_router
from api.routes.approvals import router as approvals_router
from api.routes.search import router as search_router
from api.routes.utils_routes import router as utils_router
from api.routes.restricted_items import router as restricted_items_router

app.include_router(health_router)
app.include_router(rag_router)
app.include_router(ingestion_router)
app.include_router(autofill_router)
app.include_router(documents_router)
app.include_router(extraction_router)
app.include_router(feedback_router)
app.include_router(templates_router)
app.include_router(approvals_router)
app.include_router(search_router)
app.include_router(utils_router)
app.include_router(restricted_items_router)


# ─────────────────────────────────────────────────────────────
#  REGISTER v2 ROUTE MODULES  (entity-centric platform)
# ─────────────────────────────────────────────────────────────

from api.v2.health import router as v2_health_router
from api.v2.ingest import router as v2_ingest_router
from api.v2.entity import router as v2_entity_router
from api.v2.search import router as v2_search_router

app.include_router(v2_health_router)
app.include_router(v2_ingest_router)
app.include_router(v2_entity_router)
app.include_router(v2_search_router)
