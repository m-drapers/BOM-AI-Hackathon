"""AB test: Sparse retrieval methods — BM25 vs BM25+ vs CDR vs BM25F.

Tests 4 sparse retrieval scoring methods combined with vector search via RRF,
all on the same production ChromaDB data (sentence-aware + enriched chunks).

Usage:
    cd teams/team5/backend
    set -a && source ../.env && set +a
    .venv/bin/python -m tests.ab_chunking.run_sparse
"""

import asyncio
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

import chromadb
import numpy as np

from connectors.embeddings import get_embedding_function
from tests.ab_chunking.judge import judge_batch
from tests.ab_chunking.metrics import (
    recall_at_k, precision_at_k, mrr, aggregate_metrics, compare_to_baseline,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = Path("/home/ralph/Projects/Hackathon-BOM-IKNL/data/chromadb")
QUERIES_PATH = Path(__file__).resolve().parent / "queries.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Sparse retrieval implementations
# ---------------------------------------------------------------------------

class BM25Standard:
    """Standard BM25 via fastembed (current production)."""
    name = "bm25_standard"

    def __init__(self, docs, doc_ids):
        from fastembed.sparse.bm25 import Bm25
        self._bm25 = Bm25(model_name="Qdrant/bm25", language="dutch")
        self._doc_ids = doc_ids
        self._embeddings = list(self._bm25.passage_embed(docs))

    def search(self, query: str, n: int = 20) -> list[tuple[str, float]]:
        q_emb = list(self._bm25.query_embed(query))[0]
        q_dict = dict(zip(q_emb.indices, q_emb.values))
        scores = []
        for i, d_emb in enumerate(self._embeddings):
            d_dict = dict(zip(d_emb.indices, d_emb.values))
            common = set(d_emb.indices) & set(q_emb.indices)
            score = sum(d_dict[idx] * q_dict[idx] for idx in common)
            if score > 0:
                scores.append((self._doc_ids[i], score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:n]


class BM25Plus:
    """BM25+ via bm25s library — fixes long-document bias."""
    name = "bm25_plus"

    def __init__(self, docs, doc_ids):
        import bm25s
        import bm25s.tokenization
        self._doc_ids = doc_ids
        self._model = bm25s.BM25(method="bm25+")
        # Tokenize with simple whitespace + lowercase
        tokens = bm25s.tokenization.tokenize(docs, lower=True, stopwords=None)
        self._model.index(tokens)
        self._tokenize = lambda q: bm25s.tokenization.tokenize([q], lower=True, stopwords=None)

    def search(self, query: str, n: int = 20) -> list[tuple[str, float]]:
        q_tokens = self._tokenize(query)
        results, scores = self._model.retrieve(q_tokens, k=n)
        output = []
        for idx, score in zip(results[0], scores[0]):
            if score > 0 and idx < len(self._doc_ids):
                output.append((self._doc_ids[idx], float(score)))
        return output


class CoverDensity:
    """Cover Density Ranking — scores based on term proximity."""
    name = "cover_density"

    def __init__(self, docs, doc_ids):
        self._doc_ids = doc_ids
        # Build positional index: doc_idx -> {term -> [positions]}
        self._positions = []
        for doc in docs:
            words = doc.lower().split()
            pos_map = defaultdict(list)
            for i, w in enumerate(words):
                # Strip punctuation
                clean = re.sub(r'[^\w]', '', w)
                if clean:
                    pos_map[clean].append(i)
            self._positions.append(pos_map)

    def _find_covers(self, query_terms: list[str], pos_map: dict) -> list[tuple[int, int]]:
        """Find minimal covers — shortest spans containing all query terms."""
        # Get positions for each term that exists in the doc
        term_positions = {}
        for t in query_terms:
            if t in pos_map:
                term_positions[t] = pos_map[t]

        if len(term_positions) < 2:
            # Single term or no match — no cover possible
            return []

        # Merge all positions with term labels
        events = []
        for term, positions in term_positions.items():
            for pos in positions:
                events.append((pos, term))
        events.sort()

        # Sliding window to find minimal covers
        covers = []
        term_count = defaultdict(int)
        distinct = 0
        target = len(term_positions)
        left = 0

        for right_idx, (right_pos, right_term) in enumerate(events):
            term_count[right_term] += 1
            if term_count[right_term] == 1:
                distinct += 1

            while distinct == target:
                left_pos, left_term = events[left]
                covers.append((left_pos, right_pos))
                term_count[left_term] -= 1
                if term_count[left_term] == 0:
                    distinct -= 1
                left += 1

        return covers

    def _score_covers(self, covers: list[tuple[int, int]], lam: int = 16) -> float:
        """Score covers using CDR formula: S = Σ I(p,q)."""
        score = 0.0
        for p, q in covers:
            span = q - p + 1
            if span <= lam:
                score += 1.0
            else:
                score += lam / span
        return score

    def search(self, query: str, n: int = 20) -> list[tuple[str, float]]:
        query_terms = [re.sub(r'[^\w]', '', w.lower()) for w in query.split() if w.strip()]
        query_terms = [t for t in query_terms if t]

        scores = []
        for i, pos_map in enumerate(self._positions):
            # Coordination level: count of distinct query terms present
            matched = sum(1 for t in query_terms if t in pos_map)
            if matched == 0:
                continue

            # Cover density score
            covers = self._find_covers(query_terms, pos_map)
            cdr_score = self._score_covers(covers) if covers else 0.0

            # Combined: coordination level * 1000 + CDR score
            # This ensures higher coordination level always wins
            combined = matched * 1000 + cdr_score
            scores.append((self._doc_ids[i], combined))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:n]


class BM25Field:
    """BM25F-style scoring — weights title/kankersoort prefix higher."""
    name = "bm25_field"

    def __init__(self, docs, doc_ids, metas):
        import bm25s
        import bm25s.tokenization
        self._doc_ids = doc_ids

        # Split each doc into title field and body field
        # Our enriched format: "Title — kankersoort: body text"
        title_docs = []
        body_docs = []
        for doc, meta in zip(docs, metas):
            title = meta.get("title", "")
            kankersoort = meta.get("kankersoort", "")
            title_field = f"{title} {kankersoort} {title} {kankersoort}"  # repeat 2x for weight
            # Strip the prefix from body
            body = doc
            sep_idx = doc.find(": ")
            if sep_idx > 0 and sep_idx < 100:
                body = doc[sep_idx + 2:]
            title_docs.append(title_field)
            body_docs.append(body)

        # Concatenate weighted fields
        combined = [f"{t} {b}" for t, b in zip(title_docs, body_docs)]

        self._model = bm25s.BM25(method="robertson")
        tokens = bm25s.tokenization.tokenize(combined, lower=True, stopwords=None)
        self._model.index(tokens)
        self._tokenize = lambda q: bm25s.tokenization.tokenize([q], lower=True, stopwords=None)

    def search(self, query: str, n: int = 20) -> list[tuple[str, float]]:
        q_tokens = self._tokenize(query)
        results, scores = self._model.retrieve(q_tokens, k=n)
        output = []
        for idx, score in zip(results[0], scores[0]):
            if score > 0 and idx < len(self._doc_ids):
                output.append((self._doc_ids[idx], float(score)))
        return output


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def rrf_fuse(vector_ranking: list[str], sparse_ranking: list[tuple[str, float]],
             vector_weight: float = 0.7, sparse_weight: float = 0.3, k: int = 60,
             n: int = 5) -> list[str]:
    """Fuse vector and sparse rankings using RRF."""
    v_rank = {doc_id: rank for rank, doc_id in enumerate(vector_ranking)}
    s_rank = {doc_id: rank for rank, (doc_id, _) in enumerate(sparse_ranking)}

    all_ids = set(vector_ranking) | {doc_id for doc_id, _ in sparse_ranking}
    scores = {}
    for doc_id in all_ids:
        score = 0.0
        if doc_id in v_rank:
            score += vector_weight / (k + v_rank[doc_id])
        if doc_id in s_rank:
            score += sparse_weight / (k + s_rank[doc_id])
        scores[doc_id] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in ranked[:n]]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _is_url_relevant(url, q):
    url_lower = url.lower()
    patterns = q.get("relevant_url_patterns", [])
    sections = q.get("relevant_sections", [])
    return any(p.lower() in url_lower for p in patterns) and (
        not sections or any(s.lower() in url_lower for s in sections)
    )


async def run():
    logger.info("=== Sparse Methods AB Test ===")

    # Load ChromaDB collection
    ef = get_embedding_function()
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    col = client.get_collection("kanker_nl", embedding_function=ef)

    # Get all docs for sparse index building
    logger.info("Loading all documents from ChromaDB...")
    all_data = col.get(include=["documents", "metadatas"])
    doc_ids = all_data["ids"]
    docs = all_data["documents"]
    metas = all_data["metadatas"]
    id_to_meta = dict(zip(doc_ids, metas))
    logger.info("Loaded %d documents", len(docs))

    # Build sparse indices
    logger.info("Building BM25 standard index...")
    bm25_std = BM25Standard(docs, doc_ids)

    logger.info("Building BM25+ index...")
    bm25_plus = BM25Plus(docs, doc_ids)

    logger.info("Building Cover Density index...")
    cdr = CoverDensity(docs, doc_ids)

    logger.info("Building BM25F index...")
    bm25f = BM25Field(docs, doc_ids, metas)

    # Load queries
    with open(QUERIES_PATH) as f:
        queries = json.load(f)["kanker_nl"]

    # Test each sparse method combined with vector search via RRF
    methods = [
        ("vector_only", None),
        ("rrf_bm25_std", bm25_std),
        ("rrf_bm25_plus", bm25_plus),
        ("rrf_cdr", cdr),
        ("rrf_bm25f", bm25f),
    ]

    all_results = {}

    for method_name, sparse_searcher in methods:
        logger.info("Running: %s", method_name)
        per_query = []

        for qdef in queries:
            query = qdef["query"]

            # Vector search (same for all)
            vec_results = col.query(query_texts=[query], n_results=20)
            vec_ids = vec_results["ids"][0] if vec_results["ids"][0] else []
            vec_docs = vec_results["documents"][0] if vec_results["documents"][0] else []
            vec_metas = vec_results["metadatas"][0] if vec_results["metadatas"][0] else []

            if sparse_searcher is None:
                # Vector only
                top_ids = vec_ids[:5]
                top_docs = vec_docs[:5]
                top_metas = vec_metas[:5]
            else:
                # RRF fusion
                sparse_results = sparse_searcher.search(query, n=20)
                fused_ids = rrf_fuse(vec_ids, sparse_results, vector_weight=0.7, sparse_weight=0.3, k=60, n=5)
                top_ids = fused_ids
                top_docs = []
                top_metas = []
                for did in fused_ids:
                    # Find doc text and meta
                    if did in id_to_meta:
                        top_metas.append(id_to_meta[did])
                    else:
                        top_metas.append({})
                    idx = doc_ids.index(did) if did in doc_ids else -1
                    top_docs.append(docs[idx] if idx >= 0 else "")

            url_rel = [1.0 if _is_url_relevant(m.get("url", ""), qdef) else 0.0 for m in top_metas]
            llm_rel = await judge_batch(qdef["query"], top_docs) if top_docs else []
            combined = [max(u, l) for u, l in zip(url_rel, llm_rel)] if top_docs else []
            total_rel = max(sum(url_rel), 1)

            per_query.append({
                "query_id": qdef["id"],
                "category": qdef["category"],
                "recall_at_5": recall_at_k(sum(1 for r in combined if r > 0.5), total_rel),
                "precision_at_5": precision_at_k(combined),
                "mrr": mrr(combined),
            })

        agg = aggregate_metrics(per_query)

        # Per-category
        cats = {}
        for pq in per_query:
            cats.setdefault(pq["category"], []).append(pq)

        cat_aggs = {}
        for cat, pqs in sorted(cats.items()):
            n_cat = len(pqs)
            cat_aggs[cat] = {
                "recall_at_5": sum(q["recall_at_5"] for q in pqs) / n_cat,
                "precision_at_5": sum(q["precision_at_5"] for q in pqs) / n_cat,
                "mrr": sum(q["mrr"] for q in pqs) / n_cat,
            }

        all_results[method_name] = {"aggregate": agg, "per_category": cat_aggs, "per_query": per_query}

        logger.info("  %s: R@5=%.3f P@5=%.3f MRR=%.3f", method_name,
                     agg["recall_at_5"], agg["precision_at_5"], agg["mrr"])
        for cat, ca in sorted(cat_aggs.items()):
            logger.info("    %s: R@5=%.3f P@5=%.3f MRR=%.3f", cat,
                         ca["recall_at_5"], ca["precision_at_5"], ca["mrr"])

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "sparse_methods_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    logger.info("Results saved to %s", RESULTS_DIR / "sparse_methods_results.json")

    # Print comparison table
    print("\n=== SPARSE METHODS COMPARISON ===")
    print(f"{'Method':<20} {'R@5':>6} {'P@5':>6} {'MRR':>6} | {'symptom':>8} {'treatment':>10} {'living':>8}")
    print("-" * 85)
    baseline = all_results["vector_only"]["aggregate"]
    for name, data in all_results.items():
        agg = data["aggregate"]
        cats = data["per_category"]
        s_mrr = cats.get("symptom", {}).get("mrr", 0)
        t_mrr = cats.get("treatment", {}).get("mrr", 0)
        l_mrr = cats.get("living_with", {}).get("mrr", 0)
        delta = ""
        if name != "vector_only":
            d = compare_to_baseline(baseline, agg)
            delta = f" ({d.get('mrr_delta_pct', 0):+.1f}%)"
        print(f"{name:<20} {agg['recall_at_5']:6.3f} {agg['precision_at_5']:6.3f} {agg['mrr']:6.3f}{delta} | {s_mrr:8.3f} {t_mrr:10.3f} {l_mrr:8.3f}")

    logger.info("=== Done ===")


if __name__ == "__main__":
    asyncio.run(run())
