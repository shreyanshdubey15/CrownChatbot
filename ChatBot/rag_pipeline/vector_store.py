import weaviate
from weaviate.classes.init import Auth
from rag_pipeline.embeddings import EmbeddingModel


class WeaviateVectorStore:

    def __init__(self, client=None):
        self.client = client or weaviate.connect_to_local()
        self.collection_name = "KnowledgeBase"

        # Create collection if not exists
        if not self.client.collections.exists(self.collection_name):
            self.client.collections.create(
                name=self.collection_name,
                vectorizer_config=None
            )

        self.collection = self.client.collections.get(self.collection_name)
        self.embedder = EmbeddingModel()

    def store_chunks(self, chunks):

        texts = [chunk.page_content for chunk in chunks]
        vectors = self.embedder.embed_documents(texts)

        stored = 0
        with self.collection.batch.dynamic() as batch:

            for chunk, vector in zip(chunks, vectors):
                # Safely coerce page to int (some loaders return None or str)
                page = chunk.metadata.get("page", 0)
                try:
                    page = int(page) if page is not None else 0
                except (ValueError, TypeError):
                    page = 0

                batch.add_object(
                    properties={
                        "text": chunk.page_content,
                        "source": chunk.metadata.get("source", "unknown"),
                        "page": page,
                        "chunk_id": chunk.metadata.get("chunk_id", 0),
                        "extraction_method": chunk.metadata.get("extraction_method", "unknown"),
                    },
                    vector=vector
                )
                stored += 1

        print(f"[VECTOR DB] Stored {stored} chunks in Weaviate successfully!")

    def delete_all(self):
        if self.client.collections.exists(self.collection_name):
            self.client.collections.delete(self.collection_name)

            # Re-create collection for immediate use
            self.client.collections.create(
                name=self.collection_name,
                vectorizer_config=None
            )
            self.collection = self.client.collections.get(self.collection_name)

        print("[OK] All chunks deleted from Weaviate!")
