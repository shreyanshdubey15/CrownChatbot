"""
Unified LLM Client — Supports Groq and Ollama (native)
========================================================
Provides a single interface for sync and async LLM calls.
Swap between Groq (cloud) and Ollama (local/cloud) via the LLM_PROVIDER setting.

For Ollama, uses the native `ollama` Python package (supports cloud models
like rnj-1:8b-cloud that need Ollama's built-in auth).

A thin wrapper maps the ollama response to the same shape as Groq/OpenAI
so the rest of the codebase doesn't need any changes:
    response.choices[0].message.content

Usage:
    from rag_pipeline.llm_client import get_sync_client, get_async_client, get_model

    client = get_sync_client()
    response = client.chat.completions.create(
        model=get_model("chat"),
        messages=[...],
        temperature=0,
    )
"""

import os
from dotenv import load_dotenv
from config.settings import settings

load_dotenv()


# ══════════════════════════════════════════════════════════════
#  Ollama → OpenAI-shape Compatibility Wrapper
#  Maps ollama's response.message.content
#  to    response.choices[0].message.content
# ══════════════════════════════════════════════════════════════

class _OllamaMessageShim:
    """Shim so `choice.message.content` works."""
    def __init__(self, ollama_message):
        self.content = ollama_message.content
        self.role = ollama_message.role


class _OllamaChoiceShim:
    """Shim so `response.choices[0]` works."""
    def __init__(self, ollama_message):
        self.message = _OllamaMessageShim(ollama_message)


class _OllamaChatResponseShim:
    """Shim so `response.choices[0].message.content` works."""
    def __init__(self, ollama_response):
        self.choices = [_OllamaChoiceShim(ollama_response.message)]
        self.model = ollama_response.model
        self._raw = ollama_response


class _OllamaSyncCompletions:
    """Sync wrapper: `client.chat.completions.create(...)` → ollama.Client.chat(...)"""
    def __init__(self, ollama_client):
        self._client = ollama_client

    def create(self, *, model, messages, temperature=0, max_tokens=None, **kwargs):
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        response = self._client.chat(
            model=model,
            messages=[dict(m) if not isinstance(m, dict) else m for m in messages],
            options=options if options else None,
        )
        return _OllamaChatResponseShim(response)


class _OllamaAsyncCompletions:
    """Async wrapper: `await client.chat.completions.create(...)` → ollama.AsyncClient.chat(...)"""
    def __init__(self, ollama_async_client):
        self._client = ollama_async_client

    async def create(self, *, model, messages, temperature=0, max_tokens=None, **kwargs):
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        response = await self._client.chat(
            model=model,
            messages=[dict(m) if not isinstance(m, dict) else m for m in messages],
            options=options if options else None,
        )
        return _OllamaChatResponseShim(response)


class _ChatNamespace:
    """Namespace so `client.chat.completions` exists."""
    def __init__(self, completions):
        self.completions = completions


class _OllamaSyncClientWrapper:
    """Full wrapper: `client.chat.completions.create(...)` using native ollama."""
    def __init__(self, ollama_client):
        self.chat = _ChatNamespace(_OllamaSyncCompletions(ollama_client))


class _OllamaAsyncClientWrapper:
    """Full async wrapper: `await client.chat.completions.create(...)` using native ollama."""
    def __init__(self, ollama_async_client):
        self.chat = _ChatNamespace(_OllamaAsyncCompletions(ollama_async_client))


# ══════════════════════════════════════════════════════════════
#  Provider Helpers
# ══════════════════════════════════════════════════════════════

def _get_provider() -> str:
    """Return the active LLM provider ('groq' or 'ollama')."""
    provider = os.getenv("LLM_PROVIDER", settings.LLM_PROVIDER).lower().strip()
    if provider not in ("groq", "ollama"):
        raise ValueError(f"Invalid LLM_PROVIDER '{provider}'. Must be 'groq' or 'ollama'.")
    return provider


def _get_timeout():
    """Return the appropriate timeout for the active provider."""
    provider = _get_provider()
    if provider == "groq":
        return float(os.getenv("LLM_TIMEOUT_SECONDS", settings.LLM_TIMEOUT_SECONDS))
    else:
        return float(os.getenv("OLLAMA_TIMEOUT_SECONDS", settings.OLLAMA_TIMEOUT_SECONDS))


# ══════════════════════════════════════════════════════════════
#  Sync Client
# ══════════════════════════════════════════════════════════════
def get_sync_client():
    """
    Return a synchronous LLM client.
    Groq → groq.Groq   (native)
    Ollama → ollama.Client wrapped to match Groq/OpenAI interface.
    """
    provider = _get_provider()
    timeout = _get_timeout()

    if provider == "groq":
        from groq import Groq
        return Groq(
            api_key=os.getenv("GROQ_API_KEY", settings.GROQ_API_KEY),
            timeout=timeout,
        )

    else:  # ollama
        import ollama as _ollama
        host = os.getenv("OLLAMA_BASE_URL", settings.OLLAMA_BASE_URL)
        client = _ollama.Client(host=host, timeout=timeout)
        return _OllamaSyncClientWrapper(client)


# ══════════════════════════════════════════════════════════════
#  Async Client
# ══════════════════════════════════════════════════════════════
def get_async_client():
    """
    Return an asynchronous LLM client.
    Groq → groq.AsyncGroq   (native)
    Ollama → ollama.AsyncClient wrapped to match Groq/OpenAI interface.
    """
    provider = _get_provider()
    timeout = _get_timeout()

    if provider == "groq":
        from groq import AsyncGroq
        return AsyncGroq(
            api_key=os.getenv("GROQ_API_KEY", settings.GROQ_API_KEY),
            timeout=timeout,
        )

    else:  # ollama
        import ollama as _ollama
        host = os.getenv("OLLAMA_BASE_URL", settings.OLLAMA_BASE_URL)
        client = _ollama.AsyncClient(host=host, timeout=timeout)
        return _OllamaAsyncClientWrapper(client)


# ══════════════════════════════════════════════════════════════
#  Model Name Resolution
# ══════════════════════════════════════════════════════════════
def get_model(purpose: str = "chat") -> str:
    """
    Return the correct model name for the active provider and purpose.

    Purposes:
        "chat"       — RAG chatbot / conversational
        "primary"    — Primary extraction LLM
        "validator"  — Validation LLM
        "classifier" — Document classifier
        "detect"     — Form field detection
        "extract"    — Form field extraction
    """
    provider = _get_provider()

    if provider == "groq":
        mapping = {
            "chat": os.getenv("PRIMARY_MODEL", settings.PRIMARY_MODEL),
            "primary": os.getenv("PRIMARY_MODEL", settings.PRIMARY_MODEL),
            "validator": os.getenv("VALIDATOR_MODEL", settings.VALIDATOR_MODEL),
            "classifier": os.getenv("CLASSIFIER_MODEL", settings.CLASSIFIER_MODEL),
            "detect": "llama-3.3-70b-versatile",
            "extract": "llama-3.3-70b-versatile",
        }
    else:  # ollama
        mapping = {
            "chat": os.getenv("OLLAMA_CHAT_MODEL", settings.OLLAMA_CHAT_MODEL),
            "primary": os.getenv("OLLAMA_PRIMARY_MODEL", settings.OLLAMA_PRIMARY_MODEL),
            "validator": os.getenv("OLLAMA_VALIDATOR_MODEL", settings.OLLAMA_VALIDATOR_MODEL),
            "classifier": os.getenv("OLLAMA_CLASSIFIER_MODEL", settings.OLLAMA_CLASSIFIER_MODEL),
            "detect": os.getenv("OLLAMA_DETECT_MODEL", settings.OLLAMA_DETECT_MODEL),
            "extract": os.getenv("OLLAMA_EXTRACT_MODEL", settings.OLLAMA_EXTRACT_MODEL),
        }

    return mapping.get(purpose, mapping["chat"])


# ══════════════════════════════════════════════════════════════
#  Provider Info (health checks / UI)
# ══════════════════════════════════════════════════════════════
def get_provider_info() -> dict:
    """Return a dict describing the active LLM backend."""
    provider = _get_provider()
    if provider == "groq":
        return {
            "provider": "groq",
            "base_url": "https://api.groq.com",
            "chat_model": get_model("chat"),
            "primary_model": get_model("primary"),
            "has_api_key": bool(os.getenv("GROQ_API_KEY", settings.GROQ_API_KEY)),
        }
    else:
        base_url = os.getenv("OLLAMA_BASE_URL", settings.OLLAMA_BASE_URL)
        return {
            "provider": "ollama",
            "base_url": base_url,
            "chat_model": get_model("chat"),
            "primary_model": get_model("primary"),
            "has_api_key": True,
        }
