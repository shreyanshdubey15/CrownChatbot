from rag_pipeline.loader import load_documents
from rag_pipeline.chunker import chunk_documents
from rag_pipeline.embeddings import EmbeddingModel


docs = load_documents()
chunks = chunk_documents(docs)

texts = [chunk.page_content for chunk in chunks]

embedder = EmbeddingModel()
vectors = embedder.embed_documents(texts)

print(f"Chunks: {len(chunks)}")
print(f"Vector shape of first chunk: {len(vectors[0])}")
