from rag_pipeline.loader import load_documents
from rag_pipeline.chunker import chunk_documents
from rag_pipeline.vector_store import WeaviateVectorStore


docs = load_documents()
chunks = chunk_documents(docs)

store = WeaviateVectorStore()
store.store_chunks(chunks)
