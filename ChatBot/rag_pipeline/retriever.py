"""
Hybrid Retriever for RAG Pipeline
===================================
BM25 + Vector search with Reciprocal Rank Fusion (RRF)
on the KnowledgeBase collection.

- Vector search: semantic similarity (understands meaning)
- BM25 search: keyword matching (catches exact IDs, names, numbers)
- RRF fusion: merges both ranked lists for best of both worlds
"""

import hashlib
import logging
import weaviate
from weaviate.classes.query import MetadataQuery
from rag_pipeline.embeddings import EmbeddingModel

logger = logging.getLogger("retriever")


class Retriever:

    def __init__(self, client=None):
        self.client = client or weaviate.connect_to_local()
        self.collection = self.client.collections.get("KnowledgeBase")
        self.embedder = EmbeddingModel()

    def search(self, query, top_k=5):
        """
        Hybrid search: BM25 + Vector with RRF fusion.
        Returns top_k most relevant document chunks.
        """
        logger.debug("[SEARCH] Hybrid search: '%s'  top_k=%d", query[:80], top_k)
        # Run both searches in parallel-ish (sequential but fast)
        vector_results = self._vector_search(query, top_k=top_k * 3)
        bm25_results = self._bm25_search(query, top_k=top_k * 3)

        # Fuse results using RRF
        if vector_results and bm25_results:
            fused = self._reciprocal_rank_fusion(vector_results, bm25_results)
        elif vector_results:
            fused = vector_results
        elif bm25_results:
            fused = bm25_results
        else:
            fused = []

        # Deduplicate by content similarity
        fused = self._deduplicate(fused)

        return fused[:top_k]

    def _vector_search(self, query, top_k=15):
        """Dense vector (semantic) search."""
        try:
            query_vector = self.embedder.embed_query(query)
            results = self.collection.query.near_vector(
                near_vector=query_vector,
                limit=top_k,
                return_metadata=MetadataQuery(distance=True),
            )
            return self._parse_results(results, source="vector")
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

    def _bm25_search(self, query, top_k=15):
        """Sparse BM25 (keyword) search — catches exact names, IDs, numbers."""
        try:
            results = self.collection.query.bm25(
                query=query,
                limit=top_k,
                return_metadata=MetadataQuery(score=True),
            )
            return self._parse_results(results, source="bm25")
        except Exception as e:
            logger.warning("BM25 search failed: %s", e)
            return []

    def _parse_results(self, results, source="unknown"):
        """Parse Weaviate results into standardized dicts."""
        documents = []
        for obj in results.objects:
            score = 0.0
            if hasattr(obj, "metadata"):
                if hasattr(obj.metadata, "distance") and obj.metadata.distance is not None:
                    score = max(0.0, 1.0 - obj.metadata.distance)
                elif hasattr(obj.metadata, "score") and obj.metadata.score is not None:
                    score = obj.metadata.score

            documents.append({
                "text": obj.properties.get("text", ""),
                "source": obj.properties.get("source"),
                "page": obj.properties.get("page"),
                "chunk_id": obj.properties.get("chunk_id"),
                "score": score,
                "retrieval_source": source,
            })
        return documents

    def _reciprocal_rank_fusion(
        self,
        vector_results,
        bm25_results,
        vector_weight=0.65,
        bm25_weight=0.35,
        k=60,
    ):
        """
        Reciprocal Rank Fusion (RRF) — merges two ranked lists.
        RRF score = Σ (weight / (k + rank))
        k=60 is the standard constant from the RRF paper.
        """
        scores = {}
        docs = {}

        for rank, doc in enumerate(vector_results):
            content_hash = hashlib.md5(doc["text"][:300].encode()).hexdigest()
            rrf_score = vector_weight / (k + rank + 1)
            scores[content_hash] = scores.get(content_hash, 0.0) + rrf_score
            docs[content_hash] = doc
            docs[content_hash]["retrieval_source"] = "vector"

        for rank, doc in enumerate(bm25_results):
            content_hash = hashlib.md5(doc["text"][:300].encode()).hexdigest()
            rrf_score = bm25_weight / (k + rank + 1)
            scores[content_hash] = scores.get(content_hash, 0.0) + rrf_score
            if content_hash in docs:
                docs[content_hash]["retrieval_source"] = "hybrid"
            else:
                docs[content_hash] = doc
                docs[content_hash]["retrieval_source"] = "bm25"

        sorted_hashes = sorted(scores.keys(), key=lambda h: scores[h], reverse=True)

        results = []
        for h in sorted_hashes:
            doc = docs[h]
            doc["rrf_score"] = scores[h]
            results.append(doc)

        return results

    def _deduplicate(self, results, similarity_threshold=0.85):
        """Remove near-duplicate chunks (same content, different chunk IDs)."""
        seen_texts = []
        deduped = []

        for doc in results:
            text = doc["text"].strip()
            is_dup = False
            for seen in seen_texts:
                # Quick check: if one is a substring of the other
                if text in seen or seen in text:
                    is_dup = True
                    break
                # Token overlap check
                words_a = set(text.lower().split())
                words_b = set(seen.lower().split())
                if words_a and words_b:
                    overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                    if overlap > similarity_threshold:
                        is_dup = True
                        break
            if not is_dup:
                seen_texts.append(text)
                deduped.append(doc)

        return deduped
