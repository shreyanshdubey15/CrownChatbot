"""
RAG Routes — Ask & Define
===========================
/ask, /define
"""

import logging
from fastapi import APIRouter, HTTPException, Request, status

from api.models import Query, AskResponse, DefineQuery, DefineResponse
from utils.input_guard import check_input, sanitize_input

logger = logging.getLogger("rag.routes")
router = APIRouter(tags=["RAG"])


@router.post("/ask", response_model=AskResponse)
def ask_question(query: Query, request: Request):
    """Ask a question based on your uploaded documents."""
    try:
        # ── Input Guard — block injection before LLM ──
        guard = check_input(query.question)
        if not guard["safe"]:
            logger.warning("[GUARD] Blocked question: %s | reason: %s", query.question[:80], guard["reason"])
            return AskResponse(
                question=query.question,
                answer=guard["blocked_response"],
                sources=[],
            )
        clean_question = sanitize_input(query.question)

        logger.info("-" * 55)
        logger.info("[CHAT] QUESTION: %s", clean_question[:120])

        history = None
        if query.chat_history:
            # Guard each chat history message too
            safe_history = []
            for m in query.chat_history:
                h_guard = check_input(m.content)
                if h_guard["safe"]:
                    safe_history.append({"role": m.role, "content": sanitize_input(m.content)})
            history = safe_history if safe_history else None
            if history:
                logger.info("[CHAT] Chat history: %d prior messages", len(history))

        result = request.app.state.bot.ask(clean_question, chat_history=history)

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
    # ── Input Guard — block injection before LLM ──
    guard = check_input(query.term)
    if not guard["safe"]:
        logger.warning("[GUARD] Blocked define: %s | reason: %s", query.term[:80], guard["reason"])
        return DefineResponse(
            term=query.term,
            definition=guard["blocked_response"],
            sources=[],
        )
    clean_term = sanitize_input(query.term)

    logger.info("[DEFINE] '%s'", clean_term)
    try:
        result = request.app.state.bot.define_term(clean_term)
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


