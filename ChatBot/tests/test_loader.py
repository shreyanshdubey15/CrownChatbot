from rag_pipeline.loader import load_documents

docs = load_documents()

print(f"Loaded {len(docs)} documents\n")

print(docs[0].page_content[:500])
