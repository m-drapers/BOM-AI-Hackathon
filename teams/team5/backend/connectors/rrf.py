"""Reciprocal Rank Fusion (RRF) hybrid search.

Combines vector search (ChromaDB) with BM25 keyword search (fastembed)
and fuses results using RRF scoring.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with metadata."""
    doc_id: str
    text: str
    metadata: dict
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0


class HybridSearcher:
    """RRF-based hybrid search combining vector similarity and BM25 keyword matching.

    Usage:
        searcher = HybridSearcher(collection)
        searcher.build_bm25_index()  # one-time, after ingestion
        results = searcher.search("symptomen darmkanker", n_results=5)
    """

    def __init__(self, collection, vector_weight: float = 0.85, bm25_weight: float = 0.15, rrf_k: int = 40):
        self.collection = collection
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self._doc_ids: list[str] = []
        self._doc_texts: list[str] = []
        self._doc_metas: list[dict] = []
        self._bm25_model = None
        self._tokenize = None
        self._index_built = False

    def build_bm25_index(self) -> None:
        """Build BM25F index — field-weighted with title/kankersoort boosted.

        Uses bm25s library for BM25 scoring on field-weighted documents:
        title and kankersoort tokens are repeated 2x for higher weight.
        """
        logger.info("Building BM25F index for %s...", self.collection.name)

        all_data = self.collection.get(include=["documents", "metadatas"])
        self._doc_ids = all_data["ids"]
        self._doc_texts = all_data["documents"]
        self._doc_metas = all_data["metadatas"]

        # Build field-weighted documents: repeat title/kankersoort for boost
        import bm25s
        import bm25s.tokenization

        weighted_docs = []
        for doc, meta in zip(self._doc_texts, self._doc_metas):
            title = meta.get("title", "")
            kankersoort = meta.get("kankersoort", "")
            title_field = f"{title} {kankersoort} {title} {kankersoort}"
            # Strip enrichment prefix from body to avoid double-counting
            body = doc
            sep_idx = doc.find(": ")
            if sep_idx > 0 and sep_idx < 100:
                body = doc[sep_idx + 2:]
            weighted_docs.append(f"{title_field} {body}")

        tokens = bm25s.tokenization.tokenize(weighted_docs, lower=True, stopwords=None)
        self._bm25_model = bm25s.BM25(method="robertson")
        self._bm25_model.index(tokens)
        self._tokenize = lambda q: bm25s.tokenization.tokenize([q], lower=True, stopwords=None)
        self._index_built = True

        logger.info("BM25F index built: %d documents", len(self._doc_ids))

    def _bm25_search(self, query: str, n_results: int = 20) -> list[tuple[str, float]]:
        """Run BM25F keyword search. Returns list of (doc_id, score) sorted by score desc."""
        q_tokens = self._tokenize(query)
        results, scores = self._bm25_model.retrieve(q_tokens, k=n_results)
        output = []
        for idx, score in zip(results[0], scores[0]):
            if score > 0 and idx < len(self._doc_ids):
                output.append((self._doc_ids[idx], float(score), idx))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(doc_id, score) for doc_id, score, _ in scores[:n_results]]

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
        fetch_k: int = 20,
    ) -> list[SearchResult]:
        """Hybrid search combining vector + BM25 with RRF fusion.

        Args:
            query: Search query text
            n_results: Number of final results to return
            where: Optional ChromaDB metadata filter
            fetch_k: Number of candidates to fetch from each method before fusion
        """
        if not self._index_built:
            raise RuntimeError("Call build_bm25_index() first")

        # 1. Vector search via ChromaDB
        query_kwargs = {"query_texts": [query], "n_results": fetch_k}
        if where:
            query_kwargs["where"] = where
        vector_results = self.collection.query(**query_kwargs)

        vector_ids = vector_results["ids"][0] if vector_results["ids"][0] else []
        vector_docs = vector_results["documents"][0] if vector_results["documents"][0] else []
        vector_metas = vector_results["metadatas"][0] if vector_results["metadatas"][0] else []

        # 2. BM25 search
        bm25_results = self._bm25_search(query, n_results=fetch_k)
        bm25_ids = [doc_id for doc_id, _ in bm25_results]

        # 3. Build lookup for all candidate docs
        all_candidate_ids = set(vector_ids) | set(bm25_ids)
        id_to_text = {}
        id_to_meta = {}

        # From vector results
        for i, doc_id in enumerate(vector_ids):
            id_to_text[doc_id] = vector_docs[i]
            id_to_meta[doc_id] = vector_metas[i]

        # From BM25 results (fill in any missing)
        for doc_id in bm25_ids:
            if doc_id not in id_to_text:
                idx = self._doc_ids.index(doc_id)
                id_to_text[doc_id] = self._doc_texts[idx]
                id_to_meta[doc_id] = self._doc_metas[idx]

        # 4. Compute RRF scores
        vector_rank_map = {doc_id: rank for rank, doc_id in enumerate(vector_ids)}
        bm25_rank_map = {doc_id: rank for rank, doc_id in enumerate(bm25_ids)}

        results = []
        for doc_id in all_candidate_ids:
            v_rank = vector_rank_map.get(doc_id)
            b_rank = bm25_rank_map.get(doc_id)

            rrf_score = 0.0
            if v_rank is not None:
                rrf_score += self.vector_weight / (self.rrf_k + v_rank)
            if b_rank is not None:
                rrf_score += self.bm25_weight / (self.rrf_k + b_rank)

            results.append(SearchResult(
                doc_id=doc_id,
                text=id_to_text[doc_id],
                metadata=id_to_meta[doc_id],
                vector_rank=v_rank,
                bm25_rank=b_rank,
                rrf_score=rrf_score,
            ))

        # Sort by RRF score descending
        results.sort(key=lambda r: r.rrf_score, reverse=True)
        return results[:n_results]
