"""Fine-grained parameter tuning around the winning BM25F + RRF config.

Grid: 5 k values × 5 weight pairs × 4 title boost factors = 100 combos.

Usage:
    cd teams/team5/backend
    set -a && source ../.env && set +a
    .venv/bin/python -m tests.ab_chunking.run_finetune
"""

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

import bm25s
import bm25s.tokenization
import chromadb

from connectors.embeddings import get_embedding_function
from tests.ab_chunking.run_sparse import rrf_fuse, _is_url_relevant
from tests.ab_chunking.metrics import recall_at_k, precision_at_k, mrr, aggregate_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = Path("/home/ralph/Projects/Hackathon-BOM-IKNL/data/chromadb")
QUERIES_PATH = Path(__file__).resolve().parent / "queries.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Fine-grained grid around winners
K_VALUES = [30, 35, 40, 45, 50]
WEIGHT_PAIRS = [
    (0.88, 0.12),
    (0.86, 0.14),
    (0.85, 0.15),
    (0.83, 0.17),
    (0.80, 0.20),
]
TITLE_BOOSTS = [1.5, 2.0, 2.5, 3.0]


def build_bm25f(docs, doc_ids, metas, boost: float):
    """Build BM25F index with configurable title boost factor."""
    title_docs = []
    for doc, meta in zip(docs, metas):
        title = meta.get("title", "")
        kankersoort = meta.get("kankersoort", "")
        # Repeat title/kankersoort `boost` times
        title_field = " ".join([f"{title} {kankersoort}"] * int(boost))
        body = doc
        sep_idx = doc.find(": ")
        if sep_idx > 0 and sep_idx < 100:
            body = doc[sep_idx + 2:]
        title_docs.append(f"{title_field} {body}")

    tokens = bm25s.tokenization.tokenize(title_docs, lower=True, stopwords=None)
    model = bm25s.BM25(method="robertson")
    model.index(tokens)
    tokenize_fn = lambda q: bm25s.tokenization.tokenize([q], lower=True, stopwords=None)
    return model, tokenize_fn


def bm25f_search(model, tokenize_fn, doc_ids, query, n=20):
    q_tokens = tokenize_fn(query)
    results, scores = model.retrieve(q_tokens, k=n)
    output = []
    for idx, score in zip(results[0], scores[0]):
        if score > 0 and idx < len(doc_ids):
            output.append((doc_ids[idx], float(score)))
    return output


async def run():
    logger.info("=== Fine-Grained Parameter Tuning ===")

    ef = get_embedding_function()
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    col = client.get_collection("kanker_nl", embedding_function=ef)

    all_data = col.get(include=["documents", "metadatas"])
    doc_ids = all_data["ids"]
    docs = all_data["documents"]
    metas = all_data["metadatas"]
    id_to_meta = dict(zip(doc_ids, metas))

    with open(QUERIES_PATH) as f:
        queries = json.load(f)["kanker_nl"]

    # Pre-compute vector search
    logger.info("Pre-computing vector search...")
    vec_cache = {}
    for qdef in queries:
        res = col.query(query_texts=[qdef["query"]], n_results=20)
        vec_cache[qdef["id"]] = res["ids"][0] if res["ids"][0] else []

    # Pre-compute BM25F for each boost level
    sparse_caches = {}
    for boost in TITLE_BOOSTS:
        logger.info("Building BM25F index (boost=%.1f)...", boost)
        model, tok_fn = build_bm25f(docs, doc_ids, metas, boost)
        cache = {}
        for qdef in queries:
            cache[qdef["id"]] = bm25f_search(model, tok_fn, doc_ids, qdef["query"], n=20)
        sparse_caches[boost] = cache

    # Grid search
    total = len(K_VALUES) * len(WEIGHT_PAIRS) * len(TITLE_BOOSTS)
    logger.info("Running %d parameter combinations...", total)

    results = []
    for boost in TITLE_BOOSTS:
        sparse_cache = sparse_caches[boost]
        for k_val in K_VALUES:
            for v_w, s_w in WEIGHT_PAIRS:
                per_query = []
                for qdef in queries:
                    vec_ids = vec_cache[qdef["id"]]
                    sparse_res = sparse_cache[qdef["id"]]

                    fused = rrf_fuse(vec_ids, sparse_res, v_w, s_w, k_val, n=5)
                    top_metas = [id_to_meta.get(did, {}) for did in fused]
                    url_rel = [1.0 if _is_url_relevant(m.get("url", ""), qdef) else 0.0 for m in top_metas]
                    total_rel = max(sum(url_rel), 1)

                    per_query.append({
                        "category": qdef["category"],
                        "recall_at_5": recall_at_k(sum(1 for r in url_rel if r > 0.5), total_rel),
                        "precision_at_5": precision_at_k(url_rel),
                        "mrr": mrr(url_rel),
                    })

                agg = aggregate_metrics(per_query)
                cats = defaultdict(list)
                for pq in per_query:
                    cats[pq["category"]].append(pq)
                cat_mrr = {c: sum(q["mrr"] for q in qs) / len(qs) for c, qs in cats.items()}

                results.append({
                    "boost": boost, "k": k_val, "v_w": v_w, "s_w": s_w,
                    "mrr": agg["mrr"], "recall": agg["recall_at_5"], "precision": agg["precision_at_5"],
                    "sym_mrr": cat_mrr.get("symptom", 0),
                    "treat_mrr": cat_mrr.get("treatment", 0),
                    "live_mrr": cat_mrr.get("living_with", 0),
                })

    # Sort by MRR
    results.sort(key=lambda r: r["mrr"], reverse=True)

    print(f"\n=== TOP 15 CONFIGS (of {total}) ===")
    print(f"{'boost':>5} {'k':>4} {'v_w':>5} {'s_w':>5} | {'R@5':>6} {'P@5':>6} {'MRR':>6} | {'sym':>6} {'treat':>6} {'live':>6}")
    print("-" * 78)
    for r in results[:15]:
        print(f"{r['boost']:5.1f} {r['k']:4d} {r['v_w']:5.2f} {r['s_w']:5.2f} | "
              f"{r['recall']:6.3f} {r['precision']:6.3f} {r['mrr']:6.3f} | "
              f"{r['sym_mrr']:6.3f} {r['treat_mrr']:6.3f} {r['live_mrr']:6.3f}")

    best = results[0]
    print(f"\n=== OPTIMAL: boost={best['boost']}, k={best['k']}, "
          f"weights={best['v_w']}/{best['s_w']} -> MRR={best['mrr']:.3f} ===")

    # Best balanced (highest min across categories)
    for r in results:
        r["min_cat"] = min(r["sym_mrr"], r["treat_mrr"], r["live_mrr"])
    balanced = sorted(results, key=lambda r: r["min_cat"], reverse=True)
    bb = balanced[0]
    print(f"=== MOST BALANCED: boost={bb['boost']}, k={bb['k']}, "
          f"weights={bb['v_w']}/{bb['s_w']} -> min_cat={bb['min_cat']:.3f} "
          f"(sym={bb['sym_mrr']:.3f} treat={bb['treat_mrr']:.3f} live={bb['live_mrr']:.3f}) ===")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "finetune_grid.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("=== Done ===")


if __name__ == "__main__":
    asyncio.run(run())
