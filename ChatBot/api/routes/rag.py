"""
RAG Routes — Ask & Define
===========================
/ask, /define
"""

import logging
from fastapi import APIRouter, HTTPException, Request, status

from api.models import Query, AskResponse, DefineQuery, DefineResponse

logger = logging.getLogger("rag.routes")
router = APIRouter(tags=["RAG"])


@router.post("/ask", response_model=AskResponse)
def ask_question(query: Query, request: Request):
    """Ask a question based on your uploaded documents."""
    try:
        logger.info("-" * 55)
        logger.info("[CHAT] QUESTION: %s", query.question[:120])

        history = None
        if query.chat_history:
            history = [{"role": m.role, "content": m.content} for m in query.chat_history]
            logger.info("[CHAT] Chat history: %d prior messages", len(history))

        result = request.app.state.bot.ask(query.question, chat_history=history)

        sources = result.get("sources", [])
        answer = result.get("answer", "")
        logger.info("[CHAT] Answer: %d chars, %d sources", len(answer), len(sources))
        for src in sources[:3]:
            logger.debug("   source: %s", src.get("source", "?") if isinstance(src, dict) else str(src)[:80])
        logger.info("-" * 55)

        return AskResponse(
            question=query.question,
            answer=answer,
            sources=sources,
        )
    except Exception as e:
        logger.error("[ERR] ASK ERROR: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating answer: {str(e)}",
        )


@router.post("/define", response_model=DefineResponse)
def define_term(query: DefineQuery, request: Request):
    """Look up the meaning and function of a word or term from the uploaded documents."""
    logger.info("[DEFINE] '%s'", query.term)
    try:
        result = request.app.state.bot.define_term(query.term)
        logger.info("[DEFINE] Definition: %d chars", len(result.get("definition", "")))
        return DefineResponse(
            term=result["term"],
            definition=result["definition"],
            sources=result["sources"],
        )
    except Exception as e:
        logger.error("[ERR] DEFINE ERROR: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error defining term: {str(e)}",
        )


