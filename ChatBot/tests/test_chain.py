from rag_pipeline.chain import RAGChain

bot = RAGChain()

question = "What is this document about?"

answer = bot.ask(question)

print("\nAI Answer:\n")
print(answer)
