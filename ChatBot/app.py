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
import time
import logging

# ── HEIF shim (must run before any unstructured import) ──────
import pillow_heif
sys.modules["pi_heif"] = pillow_heif

from contextlib import asynccontextmanager

import weaviate
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from rag_pipeline.chain import RAGChain
from rag_pipeline.embeddings import EmbeddingModel
from rag_pipeline.autofill_engine import AutofillEngine
from config.constants import UPLOAD_DIR, AUTOFILL_TEMP_DIR, FRONTEND_DIR

# ─────────────────────────────────────────────────────────────
#  LOGGING CONFIGURATION — show everything in terminal
# ─────────────────────────────────────────────────────────────

LOG_FORMAT = (
    "%(asctime)s "
    "%(levelname)-8s "
    "%(name)-28s "
    "%(message)s"
)

# Force UTF-8 stdout for Windows (cp1252 can't handle special chars)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

# Reduce noise from very chatty libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("multipart").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.WARNING)
logging.getLogger("unstructured").setLevel(logging.INFO)
logging.getLogger("weaviate").setLevel(logging.WARNING)

logger = logging.getLogger("app")


# Ensure data directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUTOFILL_TEMP_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────
#  REQUEST / RESPONSE LOGGING MIDDLEWARE
# ─────────────────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request + response with timing."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        client = request.client.host if request.client else "unknown"

        # Skip noisy static-file requests
        if path.startswith("/static/"):
            return await call_next(request)

        logger.info(
            "--> %s %s %s  client=%s",
            method, path, f"?{query}" if query else "", client,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            logger.error(
                "[ERR] %s %s  %.0fms  ERROR: %s",
                method, path, elapsed, exc,
            )
            raise

        elapsed = (time.time() - start) * 1000
        status = response.status_code

        logger.info(
            "<-- %s %s  %d  %.0fms",
            method, path, status, elapsed,
        )
        return response


# ─────────────────────────────────────────────────────────────
#  LIFESPAN — startup / shutdown
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  >>> STARTING UP -- RAG Chatbot Server")
    logger.info("=" * 60)

    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.info("[OK] HEIF image support registered")

    EmbeddingModel()  # Load singleton
    logger.info("[OK] Embedding model loaded")

    # Shared Weaviate Client
    app.state.weaviate_client = weaviate.connect_to_local()
    logger.info("[OK] Weaviate client connected")

    # Initialize shared bot with shared client
    app.state.bot = RAGChain(client=app.state.weaviate_client)
    logger.info("[OK] RAG Chain initialized")

    # Initialize Autofill Engine (independent from chatbot)
    app.state.autofill_engine = AutofillEngine(weaviate_client=app.state.weaviate_client)
    logger.info("[OK] Autofill Engine initialized")

    logger.info("=" * 60)
    logger.info("  [OK] SERVER READY -- All systems operational")
    logger.info("=" * 60)

    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  [STOP] SHUTTING DOWN...")
    logger.info("=" * 60)
    if hasattr(app.state, "weaviate_client"):
        app.state.weaviate_client.close()
        logger.info("[OK] Weaviate client closed")


# ─────────────────────────────────────────────────────────────
#  APP FACTORY
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dial Phone Elite Sales Intelligence API",
    description="Carrier-Grade Telecom Sales AI — Tier-1 wholesale telecom sales strategist with RAG-powered document intelligence",
    version="2.0.0",
    lifespan=lifespan,
)

# Request logging middleware (must be added BEFORE CORS)
app.add_middleware(RequestLoggingMiddleware)

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
