"""
Document Chunker
=================
Splits documents into overlapping chunks for vector storage.
Uses settings from config/settings.py for chunk_size and overlap.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from config.settings import settings


def chunk_documents(documents):
    """
    Chunk documents using settings-driven parameters.
    Larger chunks preserve more context for retrieval.

    The splitter uses paragraph/line/sentence boundaries (in that order)
    so the loader MUST preserve \\n characters in page_content.
    """
    total_input_chars = sum(len(d.page_content) for d in documents)
    sources = {d.metadata.get("source", "?") for d in documents}
    print(f"[CHUNKER] Input: {len(documents)} doc(s), {total_input_chars} chars "
          f"from {', '.join(sources)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,          # 800 by default
        chunk_overlap=settings.CHUNK_OVERLAP,     # 200 by default
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )

    chunks = splitter.split_documents(documents)

    # Add chunk IDs and normalise whitespace within each chunk
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i
        # Collapse whitespace AFTER splitting (newlines already used for boundaries)
        chunk.page_content = " ".join(chunk.page_content.split())

    # Filter out tiny chunks that won't help retrieval
    min_len = settings.MIN_CHUNK_LENGTH  # 50 by default
    before = len(chunks)
    chunks = [c for c in chunks if len(c.page_content.strip()) >= min_len]
    filtered = before - len(chunks)

    # CRITICAL GUARD: Ensure we have chunks
    if not chunks:
        raise ValueError("Chunking produced no results - document may be empty or invalid")

    print(f"[CHUNKER] Produced {len(chunks)} chunks "
          f"(size={settings.CHUNK_SIZE}, overlap={settings.CHUNK_OVERLAP}"
          f"{f', filtered {filtered} tiny' if filtered else ''})")

    return chunks
