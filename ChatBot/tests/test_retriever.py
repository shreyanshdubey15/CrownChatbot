from rag_pipeline.retriever import Retriever


retriever = Retriever()

query = "What is this document about?"

results = retriever.search(query)

print("\nTop Results:\n")

for i, r in enumerate(results, 1):
    print(f"Result {i}:")
    print(r["text"][:300])
    print("-" * 50)
