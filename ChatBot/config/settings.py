"""
Centralized Configuration — Entity-Centric Document Intelligence Platform
==========================================================================
Single source of truth for all tunable parameters.
Environment variables override defaults via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Tier-1 enterprise configuration.
    All secrets injected via env vars — never hardcoded.
    """

    # ── Environment ──────────────────────────────────────────
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── LLM Provider Selection ────────────────────────────────
    # Options: "groq" | "ollama"
    LLM_PROVIDER: str = "groq"

    # ── Groq Configuration ────────────────────────────────────
    GROQ_API_KEY: str = ""
    PRIMARY_MODEL: str = "llama-3.1-70b-versatile"       # Extraction LLM
    VALIDATOR_MODEL: str = "llama-3.1-8b-instant"         # Validation LLM
    CLASSIFIER_MODEL: str = "llama-3.1-8b-instant"        # Doc classifier

    # ── Ollama Configuration ──────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"       # Ollama server URL
    OLLAMA_PRIMARY_MODEL: str = "llama3.1"                # Main extraction model
    OLLAMA_VALIDATOR_MODEL: str = "llama3.1"              # Validation model
    OLLAMA_CLASSIFIER_MODEL: str = "llama3.1"             # Classifier model
    OLLAMA_CHAT_MODEL: str = "llama3.1"                   # Chat / RAG model
    OLLAMA_DETECT_MODEL: str = "llama3.1"                 # Field detection model
    OLLAMA_EXTRACT_MODEL: str = "llama3.1"                # Field extraction model

    # ── Shared LLM Settings ───────────────────────────────────
    LLM_TEMPERATURE: float = 0.0                          # Compliance: deterministic
    LLM_MAX_TOKENS_EXTRACT: int = 2048
    LLM_MAX_TOKENS_VALIDATE: int = 1024
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 30                         # Groq timeout (cloud = fast)
    OLLAMA_TIMEOUT_SECONDS: int = 300                     # Ollama timeout (local = slower)

    # ── Embedding Configuration ──────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"       # 1024-dim, superior retrieval
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Layout Model Configuration ───────────────────────────
    LAYOUT_MODEL: str = "microsoft/layoutlmv3-base"
    LAYOUT_MODEL_FALLBACK: str = "naver-clova-ix/donut-base"
    LAYOUT_CONFIDENCE_THRESHOLD: float = 0.85
    ENABLE_LAYOUT_EXTRACTION: bool = True

    # ── Weaviate Configuration ───────────────────────────────
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_COLLECTION: str = "TelecomDocIntel"
    WEAVIATE_BM25_COLLECTION: str = "TelecomDocIntelBM25"

    # ── Neo4j Configuration ──────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "docintel"
    ENABLE_GRAPH: bool = True

    # ── Retrieval Configuration ──────────────────────────────
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    FUSION_TOP_K: int = 8                                  # After RRF fusion
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    RERANKER_TOP_K: int = 5
    ENABLE_RERANKER: bool = True
    BM25_WEIGHT: float = 0.3                               # In RRF fusion
    VECTOR_WEIGHT: float = 0.7

    # ── Confidence Guardrails ────────────────────────────────
    AUTOFILL_CONFIDENCE_THRESHOLD: float = 0.92            # Hard floor
    REVIEW_CONFIDENCE_THRESHOLD: float = 0.80              # "Needs Review" zone
    MEMORY_AGREEMENT_BOOST: float = 0.15
    MULTI_SOURCE_BOOST: float = 0.10
    REGEX_MATCH_BOOST: float = 0.08
    CONTRADICTION_PENALTY: float = 0.15

    # ── Chunking Configuration ───────────────────────────────
    CHUNK_SIZE: int = 800                                  # Larger for compliance docs
    CHUNK_OVERLAP: int = 200
    MIN_CHUNK_LENGTH: int = 50

    # ── Table Extraction ─────────────────────────────────────
    TABLE_EXTRACTOR: str = "camelot"                       # "camelot" | "tabula"
    TABLE_CONFIDENCE_THRESHOLD: float = 0.70

    # ── Versioned Memory ─────────────────────────────────────
    MEMORY_STORE_PATH: str = "data/entity_store"
    EVENT_LOG_PATH: str = "data/event_log"
    AUDIT_TRAIL_PATH: str = "data/audit_trail"
    ENABLE_VERSIONED_MEMORY: bool = True

    # ── Document Classification ──────────────────────────────
    DOCUMENT_CLASSES: list = [
        "kyc", "agreement", "invoice", "tax",
        "fcc", "robocall", "carrier_contract", "amendment", "unknown"
    ]

    # ── File Storage ─────────────────────────────────────────
    UPLOAD_DIR: str = "data/uploads"
    AUTOFILL_TEMP_DIR: str = "data/autofill_temp"
    MAX_FILE_SIZE_MB: int = 50

    # ── Security ─────────────────────────────────────────────
    API_KEY_HEADER: str = "X-API-Key"
    ENABLE_API_KEY_AUTH: bool = False
    API_KEYS: list = []
    ENABLE_AUDIT_LOGGING: bool = True
    ENCRYPT_PII_AT_REST: bool = False
    PII_ENCRYPTION_KEY: str = ""

    # ── Rate Limiting ────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── OCR ──────────────────────────────────────────────────
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    ENABLE_OCR_FALLBACK: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()


