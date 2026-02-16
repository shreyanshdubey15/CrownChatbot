"""
Search / Retrieval API v2
==========================
Hybrid search endpoint with BM25 + vector fusion.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/v2/search", tags=["Search v2"])


class SearchResult(BaseModel):
    text: str
    source: Optional[str] = None
    page: Optional[int] = None
    document_type: Optional[str] = None
    company_id: Optional[str] = None
    score: float = 0.0
    retrieval_source: str = "unknown"       # "vector" | "bm25" | "hybrid"


class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResult]
    retrieval_method: str = "hybrid"


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[SearchResult]
    model_used: str = ""


@router.get(
    "/hybrid",
    response_model=SearchResponse,
    summary="Hybrid search (BM25 + Vector + Rerank)",
)
def hybrid_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(8, ge=1, le=50),
    company_id: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    enable_rerank: bool = Query(True),
):
    """
    Hybrid retrieval with Reciprocal Rank Fusion.
    BM25 catches exact identifiers (EIN, FCC ID).
    Vector catches semantic matches.
    Cross-encoder reranks for precision.
    """
    from retrieval.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(request.app.state.weaviate_client)
    results = retriever.search(
        query=q,
        top_k=top_k,
        company_id=company_id,
        document_type=document_type,
        enable_rerank=enable_rerank,
    )

    return SearchResponse(
        query=q,
        total_results=len(results),
        results=[SearchResult(**r) for r in results],
        retrieval_method="hybrid" if enable_rerank else "rrf_fusion",
    )


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question with hybrid retrieval",
)
async def ask_question(
    request: Request,
    question: str,
    company_id: Optional[str] = None,
    document_type: Optional[str] = None,
):
    """
    RAG question-answering with hybrid retrieval.
    Uses the full BM25 + vector + rerank pipeline.
    """
    from retrieval.hybrid_retriever import HybridRetriever
    from rag_pipeline.llm_client import get_async_client, get_model
    from config.settings import settings

    retriever = HybridRetriever(request.app.state.weaviate_client)
    results = retriever.search(
        query=question,
        top_k=5,
        company_id=company_id,
        document_type=document_type,
    )

    if not results:
        return AskResponse(
            question=question,
            answer="I don't have enough information to answer this question based on the available documents.",
            sources=[],
            model_used=settings.PRIMARY_MODEL,
        )

    context = "\n\n---\n\n".join(
        f"[Source: {r.get('source', 'Unknown')} | Page: {r.get('page', '?')}]\n{r['text']}"
        for r in results
    )

    prompt = (
        "You are a knowledge assistant for telecom compliance documents.\n\n"
        "RULES:\n"
        "- Answer ONLY from the provided context\n"
        "- If the answer is not present, say \"I don't know based on the documents.\"\n"
        "- Do NOT guess or hallucinate\n"
        "- Be clear, professional, and cite sources\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION:\n{question}"
    )

    try:
        llm = get_async_client()
        response = await llm.chat.completions.create(
            model=get_model("primary"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    return AskResponse(
        question=question,
        answer=answer,
        sources=[SearchResult(**r) for r in results],
        model_used=settings.PRIMARY_MODEL,
    )


