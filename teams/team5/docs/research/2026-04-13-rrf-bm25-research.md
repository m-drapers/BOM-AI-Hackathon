# Research Report: Advanced BM25 Variants and RRF Fusion Strategies

**Date:** 2026-04-13
**Context:** RRF hybrid search (70/30 vector/BM25) helps treatment queries (+16% precision) but hurts living-with queries (-14% recall). Research conducted to find better fusion strategies.

## Current State

- **BM25**: fastembed `Qdrant/bm25`, Dutch stemming, basic dot-product scoring
- **RRF**: k=60, static weights 70% vector / 30% BM25
- **Per-category results on production data (30 queries):**

| Category | Vector-Only MRR | RRF MRR | Delta |
|----------|----------------|---------|-------|
| Treatment | 0.850 | 0.900 | +5.9% |
| Symptom | 0.833 | 0.767 | -7.9% |
| Living-with | 0.465 | 0.400 | -14.0% |

**Root cause**: Static weights are suboptimal. Treatment queries benefit from BM25 keyword matching (exact terms like "chemotherapie"), while living-with queries need semantic understanding (vocabulary mismatch between "vermoeidheid na kanker" and relevant content about fatigue, energy, coping).

## Key Findings

### Finding 1: BM25+ Fixes Long-Document Bias
**Source:** [Which BM25 Do You Mean? (PMC7148026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7148026/), [BM25S library](https://github.com/xhluca/bm25s)
**Relevance:** Our chunks range 50-300 words. Living-with content tends to be longer (broader topics). Standard BM25 penalizes these unfairly.
**Key insight:** BM25+ adds a constant δ (typically 1.0) to the term frequency component, ensuring documents that contain a query term at least once always get a positive boost regardless of length. The `bm25s` library supports BM25+ natively (`method="bm25+"`) with the same API. This could specifically help living-with queries where relevant longer chunks are being suppressed.

### Finding 2: Adaptive Query-Dependent Fusion is the Real Win
**Source:** [Dense-Sparse Hybrid Retrieval (emergentmind)](https://www.emergentmind.com/topics/dense-sparse-hybrid-retrieval), [Hybrid Fusion Guide (ailog.fr)](https://app.ailog.fr/en/blog/guides/hybrid-retrieval-fusion)
**Relevance:** Directly addresses our per-category divergence.
**Key insight:** Dynamic Weighted RRF uses query specificity (measured by average tf·idf of query terms) to set per-query weights. Specific queries ("chemotherapie bij eierstokkanker") get higher BM25 weight; vague queries ("hoe ga je om met vermoeidheid") get lower BM25 weight. Research shows +2-7.5% gains in Precision@1 and MRR compared to static weights. Implementation: compute query-term IDF from the corpus, average it, and scale BM25 weight proportionally.

### Finding 3: RRF k Parameter Grid Search
**Source:** [OpenSearch RRF blog](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/), [Milvus RRF docs](https://milvus.io/docs/rrf-ranker.md)
**Relevance:** We use k=60 (the default). May not be optimal for our corpus.
**Key insight:** k controls how much rank differences matter. Lower k (e.g., 20) amplifies rank differences — top results dominate more. Higher k (e.g., 100) smooths everything out. For our small result sets (n=5), lower k values may be more appropriate since we care a lot about position 1. Grid search across k=[10, 20, 40, 60, 100] with our existing test queries would determine optimal.

### Finding 4: SPLADE Handles Vocabulary Mismatch (Our Living-With Problem)
**Source:** [SPLADE explained (Pinecone)](https://www.pinecone.io/learn/splade/), [Comparing SPLADE with BM25 (Zilliz)](https://medium.com/@zilliz_learn/comparing-splade-sparse-vectors-with-bm25-53368877359f)
**Relevance:** Living-with queries fail because the query and relevant content don't share exact terms. SPLADE expands terms semantically.
**Key insight:** SPLADE uses a transformer to predict which terms in the vocabulary are relevant to each document, even if they don't appear literally. "Vermoeidheid na kanker" would activate terms like "moe", "energie", "uitgeput". However, SPLADE requires a trained model (multilingual options are limited) and adds latency. For a hackathon prototype, the adaptive weighting approach (Finding 2) gives 80% of the benefit at 10% of the complexity.

### Finding 5: BM42 — Transformer-Enhanced Sparse Retrieval
**Source:** [Qdrant BM42](https://qdrant.tech/articles/bm42/)
**Relevance:** A middle ground between BM25 and SPLADE.
**Key insight:** BM42 replaces BM25's term frequency with transformer attention weights, capturing which terms in a document are most important based on context. It preserves IDF (which works well) and fixes tokenization issues by merging subword attention. Requires `fastembed` (which we already have). However, BM42 is Qdrant-native and may not work cleanly with our ChromaDB setup.

## Recommendations

| Priority | Action | Why | Effort | Impact |
|----------|--------|-----|--------|--------|
| 1 | Implement adaptive query-dependent weights | Directly fixes living-with regression, +2-7.5% gains per research | Low | High |
| 2 | Grid search RRF k parameter [10,20,40,60,100] | k=60 may not be optimal for n=5 results | Low | Medium |
| 3 | Switch to BM25+ scoring | Fixes long-document bias affecting living-with chunks | Low | Medium |
| 4 | AB test weight classes: 90/10, 85/15, 70/30, 50/50 per query type | Empirical data needed for optimal per-category weights | Low | Medium |
| 5 | Evaluate SPLADE for Dutch medical text | Handles vocabulary mismatch but high implementation effort | High | High |

### Detailed Recommendations

#### 1. Adaptive Query-Dependent Weights (Do First)

Implement a simple query classifier that adjusts RRF weights based on query characteristics:

```
if query has specific medical terms (treatment names, cancer types):
    weights = (0.6, 0.4)  # more BM25 — keyword matching helps
elif query is broad/experiential (living-with, coping, quality of life):
    weights = (0.9, 0.1)  # mostly vector — semantic matching needed
else:
    weights = (0.7, 0.3)  # default
```

Detection: compute average IDF of query terms. High IDF = specific/rare terms = more BM25. Low IDF = common terms = more vector. Alternatively, maintain a list of section keywords: treatment terms → high BM25, experiential terms → low BM25.

#### 2. Grid Search RRF k + Weights

Run the AB test harness with a parameter grid:
- k values: [10, 20, 40, 60, 100]
- Weight pairs: [(0.9, 0.1), (0.85, 0.15), (0.7, 0.3), (0.5, 0.5)]

That's 20 combinations. With our 30 test queries and existing harness, this takes ~20 minutes. The optimal (k, weights) pair becomes the new default.

#### 3. Switch to BM25+ Scoring

Replace `fastembed`'s BM25 with `bm25s` library using `method="bm25+"`. This is a near-drop-in replacement that adds the δ bonus for long documents. Expected to improve living-with recall where relevant content tends to be in longer chunks.

## Sources

- [Which BM25 Do You Mean? — Scoring Variants Study (PMC7148026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7148026/) — Large-scale comparison of BM25, BM25+, BM25L, ATIRE variants
- [BM25S Library](https://github.com/xhluca/bm25s) — Fast BM25 with BM25+, BM25L, Lucene, ATIRE variants
- [OpenSearch RRF](https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/) — RRF k parameter guidance, recommended range [10, 100]
- [Hybrid Fusion Guide (ailog.fr)](https://app.ailog.fr/en/blog/guides/hybrid-retrieval-fusion) — Adaptive weighting, query-dependent fusion
- [Dense-Sparse Hybrid Retrieval (emergentmind)](https://www.emergentmind.com/topics/dense-sparse-hybrid-retrieval) — Dynamic Weighted RRF, Exp4Fuse
- [SPLADE Explained (Pinecone)](https://www.pinecone.io/learn/splade/) — Learned sparse retrieval for vocabulary mismatch
- [BM42 (Qdrant)](https://qdrant.tech/articles/bm42/) — Transformer-enhanced sparse retrieval
- [Hybrid Search for RAG (premai.io)](https://blog.premai.io/hybrid-search-for-rag-bm25-splade-and-vector-search-combined/) — Production hybrid search architecture
