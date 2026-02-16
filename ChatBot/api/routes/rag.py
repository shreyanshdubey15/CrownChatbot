"""
RAG Routes — Ask & Define
===========================
/ask, /define
"""

from fastapi import APIRouter, HTTPException, Request, status

from api.models import Query, AskResponse, DefineQuery, DefineResponse

router = APIRouter(tags=["RAG"])


@router.post("/ask", response_model=AskResponse)
def ask_question(query: Query, request: Request):
    """Ask a question based on your uploaded documents."""
    try:
        print(f"\n[ASK] Question: {query.question[:100]}")

        history = None
        if query.chat_history:
            history = [{"role": m.role, "content": m.content} for m in query.chat_history]
            print(f"[ASK] Chat history: {len(history)} prior messages")

        result = request.app.state.bot.ask(query.question, chat_history=history)

        sources = result.get("sources", [])
        answer = result.get("answer", "")
        print(f"[ASK] Answer: {len(answer)} chars, {len(sources)} sources")

        return AskResponse(
            question=query.question,
            answer=answer,
            sources=sources,
        )
    except Exception as e:
        print(f"[ASK ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating answer: {str(e)}",
        )


@router.post("/define", response_model=DefineResponse)
def define_term(query: DefineQuery, request: Request):
    """Look up the meaning and function of a word or term from the uploaded documents."""
    try:
        result = request.app.state.bot.define_term(query.term)
        return DefineResponse(
            term=result["term"],
            definition=result["definition"],
            sources=result["sources"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error defining term: {str(e)}",
        )


