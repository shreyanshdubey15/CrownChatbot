"""
RAG Chain — Question Answering over Uploaded Documents
=======================================================
Hybrid-retrieval backed Q&A with conversation history support.
Uses the unified LLM client wrapper (Groq / Ollama).
"""

import logging
from rag_pipeline.retriever import Retriever
from rag_pipeline.llm_client import get_sync_client, get_model
from memory.restricted_items_store import get_all_items as get_restricted_items

logger = logging.getLogger("rag.chain")


# Category display labels
_CATEGORY_LABELS = {
    "not_provided": "NOT PROVIDED (we do not offer this)",
    "illegal": "ILLEGAL (prohibited by law)",
    "scam_fraud": "SCAM / FRAUD (prohibited activity)",
}


class RAGChain:

    # How many chunks to retrieve for each query
    RETRIEVAL_TOP_K = 8

    def __init__(self, client=None):
        self.client = get_sync_client()
        self.retriever = Retriever(client=client)

    # ── Restricted Items Loader ────────────────────────────────

    def _build_restricted_context(self):
        """
        Load all restricted items and format them as a context block
        for the system prompt so the LLM knows what is blocked.
        """
        items = get_restricted_items()
        if not items:
            return ""

        lines = []
        for item in items:
            cat_label = _CATEGORY_LABELS.get(item["category"], item["category"])
            line = f"  • {item['title']} — {cat_label}"
            if item.get("description"):
                line += f" — {item['description']}"
            lines.append(line)

        return (
            f"\n\nRESTRICTED / BLOCKED ITEMS LIST ({len(items)} items):\n"
            "The following services, activities, and campaigns are explicitly RESTRICTED.\n"
            "They are either NOT provided by the company, ILLEGAL, or known SCAM/FRAUD.\n\n"
            + "\n".join(lines)
        )

    # ── System Prompt Builder ─────────────────────────────────

    def _build_system_prompt(self, context_blocks):
        """
        Build a system prompt that gives the LLM rich, sourced context
        and clear instructions for answering.
        """
        # Format each context block with its source info
        formatted_chunks = []
        for i, doc in enumerate(context_blocks, 1):
            source = doc.get("source") or "Unknown"
            page = doc.get("page")
            text = doc.get("text", "").strip()
            header = f"[Source {i}: {source}"
            if page is not None:
                header += f", Page {page}"
            header += "]"
            formatted_chunks.append(f"{header}\n{text}")

        context_text = "\n\n---\n\n".join(formatted_chunks)

        # Load restricted items context
        restricted_context = self._build_restricted_context()

        return f"""You are a document intelligence assistant for a Wholesale Voice Termination company. You answer questions based STRICTLY on what is documented in the company's uploaded documents (primarily the NOC Training Manual), the RESTRICTED ITEMS LIST, and the conversation history.

CORE BUSINESS PRINCIPLE — CLOSED-WORLD ASSUMPTION:
The company ONLY provides the services, products, and capabilities that are EXPLICITLY described in the uploaded documents (NOC Training Manual and any other uploaded files). These include:
  • Wholesale Voice Termination (international call routing, CLI routes, Non-CLI routes, CC routes)
  • Bulk SMS (web platform and API)
  • Virtual Numbers (web platform and API)
  • Global Number API
  • Non-CLI Routes
  • Related telecom services described in the documents (billing, interconnection, LCR, STIR/SHAKEN compliance, etc.)

**If a service, product, campaign, or activity is NOT mentioned in the documents as something the company provides → it is NOT provided. Say so clearly.**

RULES:
1. **ONLY what the documents say we provide = provided.** If someone asks about a service not described in the documents, respond: "This is not a service we provide. Our company specializes in [list relevant services from documents]."
2. **RESTRICTED ITEMS CHECK (HIGHEST PRIORITY)**: Before answering any question, ALWAYS check if the topic matches anything in the RESTRICTED / BLOCKED ITEMS LIST below. If it does:
   - Clearly state that this item is RESTRICTED.
   - State the category: "Not Provided", "Illegal", or "Scam/Fraud".
   - If it is "Illegal" or "Scam/Fraud", warn the user strongly and explain why.
   - Do NOT suggest workarounds or alternatives for restricted items.
   - Example: "**⚠️ Restricted Item**: IVR / Press 1 campaigns are **not provided** by the company. This is listed as a restricted service."
3. For topics that ARE covered in the documents, answer thoroughly using the document context.
4. Do NOT hallucinate or guess. If you are unsure, say so.
5. Be precise, professional, and well-structured.
6. When quoting specific facts (names, numbers, dates, IDs), cite the source — e.g. "(from <filename>, Page X)".
7. If multiple documents provide related information, synthesize them and mention all sources.
8. Use bullet points and clear formatting when listing multiple items.
9. You may refer to previous questions and answers in this conversation.
10. If someone asks "what do you provide?" or "what services do you offer?", list ONLY the services explicitly described in the documents. Also mention that there is a restricted list of things NOT provided, illegal, or scam/fraud.
11. If someone asks about something not in the documents AND not on the restricted list, say: "This is not mentioned in our documentation and is not a service we currently provide."

DOCUMENT CONTEXT ({len(context_blocks)} relevant sections retrieved):

{context_text}
{restricted_context}"""

    # ── Ask Question ──────────────────────────────────────────

    def ask(self, query, chat_history=None):
        """
        Ask a question with optional conversation history.
        Uses hybrid retrieval (BM25 + vector + RRF) for best results.

        chat_history: list of dicts with keys 'role' ("user"|"assistant") and 'content'
        """
        # 1. Retrieve relevant chunks (hybrid: BM25 + vector)
        docs = self.retriever.search(query, top_k=self.RETRIEVAL_TOP_K)

        unique_sources = set(d.get('source', '') for d in docs)
        logger.info("[RETRIEVE] %d chunks from %d docs for: '%s'", len(docs), len(unique_sources), query[:80])
        for i, d in enumerate(docs):
            src = d.get("source", "?")
            method = d.get("retrieval_source", "?")
            logger.debug("  [%d] %s (via %s) -- %s", i + 1, src, method, d['text'][:60])

        # 2. Build system prompt with sourced context
        system_prompt = self._build_system_prompt(docs)

        # 3. Assemble messages
        messages = [{"role": "system", "content": system_prompt}]

        # Inject prior conversation turns (cap to last 20 messages)
        if chat_history:
            for msg in chat_history[-20:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Current question
        messages.append({"role": "user", "content": query})

        # 4. Call LLM
        model = get_model("chat")
        logger.info("[LLM] Calling model: %s  (%d messages)", model, len(messages))

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0
        )

        answer = response.choices[0].message.content
        logger.info("[OK] Answer: %d chars", len(answer))

        return {
            "answer": answer,
            "sources": docs
        }

    # ── Define Term ───────────────────────────────────────────

    def define_term(self, term):
        """
        Look up the meaning and function of a word/term within the uploaded documents.
        Retrieves extra context (top_k=10) for richer explanations.
        """
        docs = self.retriever.search(term, top_k=10)

        # Format context with source attribution
        formatted = []
        for i, doc in enumerate(docs, 1):
            source = doc.get("source") or "Unknown"
            page = doc.get("page")
            text = doc.get("text", "").strip()
            header = f"[Source {i}: {source}"
            if page is not None:
                header += f", Page {page}"
            header += "]"
            formatted.append(f"{header}\n{text}")

        context_text = "\n\n---\n\n".join(formatted)

        system_prompt = f"""You are a world-class terminology and domain expert. Your job is to give the BEST possible explanation of any word, phrase, abbreviation, or concept.

You have two knowledge sources:
1. YOUR OWN EXPERT KNOWLEDGE — use it to provide general definitions, industry context, and background.
2. THE USER'S DOCUMENTS (below) — use them to show how this term is specifically used in their files.

COMBINE BOTH to give a comprehensive, educational answer.

FORMAT (always use these exact markdown headers):

**Definition**
Give a clear, precise definition. If it's an abbreviation, expand it first. Explain what it means in plain language. 2-3 sentences.

**How It Works**
Explain the concept in depth. How does it function? Why does it matter? What is its purpose in this domain/industry? Use bullet points for clarity:
- Key point one
- Key point two
- Key point three

**In Your Documents**
Explain specifically how this term appears and is used in the user's uploaded documents. Reference specific details, clauses, or contexts from the documents below. If the term appears in different documents or different ways, explain each.

**Example**
Give a practical, real-world example or analogy that makes the concept easy to understand.

**Related Terms**
List 3-5 related terms, concepts, or abbreviations that someone looking up this term should also know. Briefly explain each in one line.

QUALITY RULES:
- Be thorough, detailed, and educational — imagine explaining to someone who has never heard this term.
- Use bullet points and clear structure for readability.
- For abbreviations/acronyms: ALWAYS expand them and explain.
- For legal/business/technical terms: explain in simple language, then add the technical detail.
- If the term is NOT found in the documents at all, still provide the general definition from your knowledge, but note that it was not found in their specific documents.
- Write at least 150 words. Do not give short answers.

USER'S DOCUMENTS CONTEXT ({len(docs)} sections):
{context_text}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Explain everything about: \"{term}\""}
        ]

        response = self.client.chat.completions.create(
            model=get_model("chat"),
            messages=messages,
            temperature=0.2
        )
        return {
            "term": term,
            "definition": response.choices[0].message.content,
            "sources": docs
        }
