"""AB test: Vector-only vs RRF hybrid search.

Uses the winning B_sentence chunking strategy for both variants.
Compares pure vector search against RRF (vector + BM25 fusion).

Usage:
    cd teams/team5/backend
    set -a && source ../.env && set +a
    .venv/bin/python -m tests.ab_chunking.run_rrf
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path

import chromadb

from connectors.embeddings import get_embedding_function
from ingestion.vectorize import chunk_sentence_aware, enrich_chunk, strip_boilerplate
from tests.ab_chunking.judge import judge_batch
from tests.ab_chunking.metrics import recall_at_k, precision_at_k, mrr, aggregate_metrics, compare_to_baseline
from tests.ab_chunking.rrf import HybridSearcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
QUERIES_PATH = Path(__file__).resolve().parent / "queries.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
CHROMADB_TEST_PATH = DATA_DIR / "chromadb_ab_test"


def _load_data():
    """Load kanker.nl pages and sitemap metadata."""
    with open(DATA_DIR / "kanker_nl_pages_all.json", "r", encoding="utf-8") as f:
        pages = json.load(f)
    with open(DATA_DIR / "sitemap.json", "r", encoding="utf-8") as f:
        sitemap = json.load(f)
    url_meta = {entry["url"]: entry for entry in sitemap}
    return pages, url_meta


def _ingest(collection, pages, url_meta):
    """Ingest with sentence-aware chunking + enrichment (shared by both variants)."""
    all_ids, all_docs, all_metas = [], [], []
    seen_urls = set()

    for url, page in pages.items():
        text = page.get("text", "")
        if not text.strip() or "Error 503" in text[:200] or "pagina die je zocht is helaas niet beschikbaar" in text[:400]:
            continue

        norm_url = url.strip().rstrip("/")
        if norm_url.startswith("https://kanker.nl/"):
            norm_url = norm_url.replace("https://kanker.nl/", "https://www.kanker.nl/", 1)

        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)

        meta = url_meta.get(norm_url)
        if meta is None:
            continue

        title = meta.get("title", "")
        kankersoort = meta.get("kankersoort", "")
        url_hash = hashlib.md5(norm_url.encode()).hexdigest()

        chunks = chunk_sentence_aware(text)
        for i, chunk in enumerate(chunks):
            enriched = enrich_chunk(chunk, title, kankersoort)
            all_ids.append(f"rrf_{url_hash}_{i}")
            all_docs.append(enriched)
            all_metas.append({
                "kankersoort": kankersoort,
                "section": meta["section"],
                "url": meta["url"],
                "title": title,
            })

    batch_size = 500
    for i in range(0, len(all_docs), batch_size):
        end = min(i + batch_size, len(all_docs))
        collection.add(ids=all_ids[i:end], documents=all_docs[i:end], metadatas=all_metas[i:end])

    return len(all_docs)


def _is_url_relevant(url, query_def):
    url_lower = url.lower()
    patterns = query_def.get("relevant_url_patterns", [])
    sections = query_def.get("relevant_sections", [])
    pattern_match = any(p.lower() in url_lower for p in patterns)
    section_match = not sections or any(s.lower() in url_lower for s in sections)
    return pattern_match and section_match


async def run_test():
    logger.info("=== RRF Hybrid Search AB Test ===")

    ef = get_embedding_function()
    client = chromadb.PersistentClient(path=str(CHROMADB_TEST_PATH))
    collection_name = "rrf_test"

    # Clean slate
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Ingest once — shared by both variants
    pages, url_meta = _load_data()
    chunk_count = _ingest(collection, pages, url_meta)
    logger.info("Ingested %d chunks", chunk_count)

    # Build BM25 index for hybrid search
    hybrid = HybridSearcher(collection, vector_weight=0.7, bm25_weight=0.3, rrf_k=60)
    hybrid.build_bm25_index()

    # Load queries
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        queries = json.load(f)["kanker_nl"]

    # Test both variants
    for variant_name, search_fn in [
        ("vector_only", lambda q, n: _vector_search(collection, q, n)),
        ("rrf_hybrid_70_30", lambda q, n: _hybrid_search(hybrid, q, n)),
        ("rrf_hybrid_50_50", lambda q, n: _hybrid_search_balanced(hybrid, q, n)),
    ]:
        logger.info("Running variant: %s", variant_name)
        per_query = []

        for q_def in queries:
            docs, metas = search_fn(q_def["query"], 5)

            url_relevance = [1.0 if _is_url_relevant(m.get("url", ""), q_def) else 0.0 for m in metas]
            llm_relevance = await judge_batch(q_def["query"], docs) if docs else []
            combined = [max(u, l) for u, l in zip(url_relevance, llm_relevance)] if docs else []
            total_relevant = max(sum(url_relevance), 1)

            per_query.append({
                "query_id": q_def["id"],
                "query": q_def["query"],
                "category": q_def["category"],
                "recall_at_5": recall_at_k(sum(1 for r in combined if r > 0.5), total_relevant),
                "precision_at_5": precision_at_k(combined),
                "mrr": mrr(combined),
            })

        agg = aggregate_metrics(per_query)
        logger.info("  %s: R@5=%.3f P@5=%.3f MRR=%.3f",
                     variant_name, agg["recall_at_5"], agg["precision_at_5"], agg["mrr"])

    # Cleanup
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    logger.info("=== Done ===")


def _vector_search(collection, query, n_results):
    """Pure vector search (current approach)."""
    results = collection.query(query_texts=[query], n_results=n_results)
    docs = results["documents"][0] if results["documents"][0] else []
    metas = results["metadatas"][0] if results["metadatas"][0] else []
    return docs, metas


def _hybrid_search(hybrid, query, n_results):
    """RRF hybrid search (70% vector, 30% BM25)."""
    results = hybrid.search(query, n_results=n_results)
    return [r.text for r in results], [r.metadata for r in results]


def _hybrid_search_balanced(hybrid, query, n_results):
    """RRF hybrid search (50% vector, 50% BM25)."""
    hybrid.vector_weight = 0.5
    hybrid.bm25_weight = 0.5
    results = hybrid.search(query, n_results=n_results)
    hybrid.vector_weight = 0.7
    hybrid.bm25_weight = 0.3
    return [r.text for r in results], [r.metadata for r in results]


if __name__ == "__main__":
    asyncio.run(run_test())
