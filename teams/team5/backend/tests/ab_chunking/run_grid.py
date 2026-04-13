"""Grid search: RRF k parameter + weight ratios using BM25F (the winning sparse method).

Tests 20 combinations: 5 k values × 4 weight pairs.

Usage:
    cd teams/team5/backend
    set -a && source ../.env && set +a
    .venv/bin/python -m tests.ab_chunking.run_grid
"""

import asyncio
import json
import logging
from pathlib import Path

import chromadb

from connectors.embeddings import get_embedding_function
from tests.ab_chunking.run_sparse import BM25Field, rrf_fuse, _is_url_relevant
from tests.ab_chunking.metrics import recall_at_k, precision_at_k, mrr, aggregate_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = Path("/home/ralph/Projects/Hackathon-BOM-IKNL/data/chromadb")
QUERIES_PATH = Path(__file__).resolve().parent / "queries.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

K_VALUES = [10, 20, 40, 60, 100]
WEIGHT_PAIRS = [
    (0.9, 0.1),
    (0.85, 0.15),
    (0.7, 0.3),
    (0.5, 0.5),
]


async def run():
    logger.info("=== RRF Grid Search (BM25F) ===")

    ef = get_embedding_function()
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    col = client.get_collection("kanker_nl", embedding_function=ef)

    all_data = col.get(include=["documents", "metadatas"])
    doc_ids = all_data["ids"]
    docs = all_data["documents"]
    metas = all_data["metadatas"]
    id_to_meta = dict(zip(doc_ids, metas))

    logger.info("Building BM25F index...")
    bm25f = BM25Field(docs, doc_ids, metas)

    with open(QUERIES_PATH) as f:
        queries = json.load(f)["kanker_nl"]

    # Pre-compute vector search results for all queries (same across grid)
    logger.info("Pre-computing vector search for all 30 queries...")
    vec_cache = {}
    for qdef in queries:
        res = col.query(query_texts=[qdef["query"]], n_results=20)
        vec_cache[qdef["id"]] = {
            "ids": res["ids"][0] if res["ids"][0] else [],
            "docs": res["documents"][0] if res["documents"][0] else [],
            "metas": res["metadatas"][0] if res["metadatas"][0] else [],
        }

    # Pre-compute BM25F results for all queries
    logger.info("Pre-computing BM25F search for all 30 queries...")
    sparse_cache = {}
    for qdef in queries:
        sparse_cache[qdef["id"]] = bm25f.search(qdef["query"], n=20)

    # Grid search
    results = []
    logger.info("Running grid search: %d k values × %d weight pairs = %d combos",
                len(K_VALUES), len(WEIGHT_PAIRS), len(K_VALUES) * len(WEIGHT_PAIRS))

    for k_val in K_VALUES:
        for v_weight, s_weight in WEIGHT_PAIRS:
            per_query = []
            for qdef in queries:
                vec = vec_cache[qdef["id"]]
                sparse = sparse_cache[qdef["id"]]

                fused_ids = rrf_fuse(
                    vec["ids"], sparse,
                    vector_weight=v_weight, sparse_weight=s_weight,
                    k=k_val, n=5,
                )

                top_metas = [id_to_meta.get(did, {}) for did in fused_ids]
                url_rel = [1.0 if _is_url_relevant(m.get("url", ""), qdef) else 0.0 for m in top_metas]
                # URL-only scoring (no LLM judge — faster for grid search)
                total_rel = max(sum(url_rel), 1)

                per_query.append({
                    "query_id": qdef["id"],
                    "category": qdef["category"],
                    "recall_at_5": recall_at_k(sum(1 for r in url_rel if r > 0.5), total_rel),
                    "precision_at_5": precision_at_k(url_rel),
                    "mrr": mrr(url_rel),
                })

            agg = aggregate_metrics(per_query)

            # Per-category
            cats = {}
            for pq in per_query:
                cats.setdefault(pq["category"], []).append(pq)
            cat_aggs = {}
            for cat, pqs in cats.items():
                n_c = len(pqs)
                cat_aggs[cat] = {
                    "mrr": sum(q["mrr"] for q in pqs) / n_c,
                }

            entry = {
                "k": k_val,
                "vector_weight": v_weight,
                "sparse_weight": s_weight,
                "recall_at_5": agg["recall_at_5"],
                "precision_at_5": agg["precision_at_5"],
                "mrr": agg["mrr"],
                "living_mrr": cat_aggs.get("living_with", {}).get("mrr", 0),
                "treatment_mrr": cat_aggs.get("treatment", {}).get("mrr", 0),
                "symptom_mrr": cat_aggs.get("symptom", {}).get("mrr", 0),
            }
            results.append(entry)

    # Sort by aggregate MRR
    results.sort(key=lambda r: r["mrr"], reverse=True)

    # Print results
    print("\n=== RRF GRID SEARCH RESULTS (BM25F, sorted by MRR) ===")
    print(f"{'k':>4} {'v_w':>5} {'s_w':>5} | {'R@5':>6} {'P@5':>6} {'MRR':>6} | {'sym':>6} {'treat':>6} {'live':>6}")
    print("-" * 72)
    for r in results:
        print(f"{r['k']:4d} {r['vector_weight']:5.2f} {r['sparse_weight']:5.2f} | "
              f"{r['recall_at_5']:6.3f} {r['precision_at_5']:6.3f} {r['mrr']:6.3f} | "
              f"{r['symptom_mrr']:6.3f} {r['treatment_mrr']:6.3f} {r['living_mrr']:6.3f}")

    # Best overall
    best = results[0]
    print(f"\n=== BEST: k={best['k']}, weights={best['vector_weight']}/{best['sparse_weight']} "
          f"MRR={best['mrr']:.3f} R@5={best['recall_at_5']:.3f} P@5={best['precision_at_5']:.3f} ===")

    # Best for living-with specifically
    best_living = max(results, key=lambda r: r["living_mrr"])
    print(f"=== BEST LIVING-WITH: k={best_living['k']}, weights={best_living['vector_weight']}/{best_living['sparse_weight']} "
          f"living_MRR={best_living['living_mrr']:.3f} ===")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "grid_search_bm25f.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("=== Done ===")


if __name__ == "__main__":
    asyncio.run(run())
