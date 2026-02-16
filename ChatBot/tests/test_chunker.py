from rag_pipeline.loader import load_documents
from rag_pipeline.chunker import chunk_documents


docs = load_documents()
chunks = chunk_documents(docs)

print(f"\nLoaded docs: {len(docs)}")
print(f"Total chunks created: {len(chunks)}\n")

print("Sample chunk:\n")
print(chunks[0].page_content)
