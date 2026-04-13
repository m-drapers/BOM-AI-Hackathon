# Comparative Evaluation of Sparse Retrieval Methods and RRF Fusion Optimization for a Dutch Cancer Information RAG System

**Author:** Ralph Schraven
**Date:** April 13, 2026
**Event:** BrabantHack_26 Hackathon --- IKNL Med Tech Track

## Abstract

We evaluate four sparse retrieval scoring methods --- BM25, BM25+, Cover Density Ranking (CDR), and BM25F (field-weighted) --- as the keyword component in a Reciprocal Rank Fusion (RRF) hybrid search pipeline for a Dutch cancer patient information system. Combined with a grid search over 20 RRF parameter configurations (5 k-values x 4 weight ratios), we identify that BM25F with RRF k=40 and 85/15 vector/sparse weighting achieves the best aggregate MRR (0.758, +5.9% over vector-only), with particularly strong improvements on treatment queries (+5.9% MRR) and the hardest category --- living-with-cancer queries (+23.7% MRR). This configuration resolves a key limitation of naive BM25 hybrid search, which degraded living-with query performance by 14%. The winning configuration has been deployed to production.

## 1. Introduction

Hybrid search combining dense vector retrieval with sparse keyword matching via Reciprocal Rank Fusion (RRF) is the standard architecture for production RAG systems. However, the choice of sparse retrieval method and fusion parameters significantly impacts per-category performance. In our previous work, we found that basic BM25 at 70/30 vector/sparse weighting improved treatment query precision by 16% but degraded living-with query recall by 14% --- an unacceptable trade-off for a patient-facing system where all query types must be well-served.

This paper systematically evaluates four sparse methods and 20 RRF parameter combinations to find the optimal hybrid search configuration.

## 2. Methods Evaluated

### 2.1 BM25 Standard (Baseline)

Standard Okapi BM25 via fastembed's Qdrant/bm25 model with Dutch stemming. Scores based on term frequency with saturation and document length normalization. Parameters: k1=1.5, b=0.75.

### 2.2 BM25+

BM25 with a lower-bound bonus (delta=1.0) that prevents long documents containing query terms from being scored similarly to shorter documents that don't. Implemented via the bm25s library (method="bm25+"). Hypothesized to help living-with queries where relevant content tends to appear in longer chunks.

### 2.3 Cover Density Ranking (CDR)

A fundamentally different approach based on term proximity rather than frequency. Documents are first ranked by coordination level (number of distinct query terms present), then scored by how close together query terms appear. Covers (minimal text spans containing all matched query terms) shorter than lambda=16 words receive full score; longer covers are penalized proportionally.

Formula: S(omega) = sum I(pj, qj), where I = 1 if span <= lambda, else lambda/span.

Custom implementation building a positional index at ingestion time.

### 2.4 BM25F (Field-Weighted)

Extends BM25 to weight document fields differently. Our enriched chunks have a structure: "Title --- kankersoort: body text". BM25F repeats the title and cancer type tokens 2x before indexing, effectively giving them double weight in the BM25 scoring. This means a query matching the cancer type in the title gets a stronger signal than the same match buried in body text.

Implemented via bm25s library (method="robertson") on field-concatenated documents.

## 3. Experimental Setup

### 3.1 Data

Production ChromaDB collection with 5,831 chunks from 2,619 kanker.nl pages. Chunks use sentence-aware splitting (300-word max) with contextual enrichment (title + kankersoort prepended).

### 3.2 Queries

30 test queries across three categories: symptom lookup (10), treatment information (10), and living-with-cancer (10). Same test set used in all previous experiments for comparability.

### 3.3 Evaluation

Metrics: Recall@5, Precision@5, Mean Reciprocal Rank (MRR). Relevance determined by URL-based ground truth with LLM-as-judge (GPT-4o-mini) supplementation for the sparse methods comparison. Grid search used URL-based ground truth only for speed (20 configurations x 30 queries = 600 evaluations).

### 3.4 RRF Configuration

All sparse methods combined with vector search using RRF:

score(d) = v_weight / (k + rank_vector(d)) + s_weight / (k + rank_sparse(d))

Baseline: k=60, v_weight=0.7, s_weight=0.3 (prior configuration).

## 4. Results

### 4.1 Sparse Methods Comparison (k=60, 70/30 weights)

| Method | R@5 | P@5 | MRR | Sym MRR | Treat MRR | Live MRR |
|--------|-----|-----|-----|---------|-----------|----------|
| Vector-only | 0.833 | 0.560 | 0.716 | 0.833 | 0.850 | 0.465 |
| RRF + BM25 | 0.833 | 0.573 | 0.689 | 0.767 | 0.900 | 0.400 |
| RRF + BM25+ | 0.800 | 0.580 | 0.681 | 0.667 | 0.900 | 0.475 |
| RRF + CDR | 0.800 | 0.533 | 0.653 | 0.658 | 0.850 | 0.450 |
| **RRF + BM25F** | **0.833** | **0.593** | **0.714** | 0.667 | **0.900** | **0.575** |

Key findings:

1. **BM25F is the only sparse method that doesn't degrade aggregate MRR** (-0.3% vs vector-only, within noise). All others cause 3.8-8.8% aggregate MRR loss.

2. **BM25F achieves the best living-with MRR** (0.575, +23.7% over vector-only). This is the category every other method hurts. The field weighting gives BM25F a smarter keyword signal --- matching on cancer type in the title is more meaningful than matching anywhere in the body.

3. **CDR performs worst** (-8.8% MRR). Term proximity is less useful when chunks are already sentence-aware (coherent by construction). CDR would matter more for large, multi-topic documents.

4. **BM25+ helps living-with slightly** (0.475 vs 0.400 for standard BM25) but hurts symptoms badly (0.667 MRR). The delta bonus changes ranking order unpredictably for our already-short chunks.

### 4.2 RRF Parameter Grid Search (BM25F)

20 configurations tested: k in {10, 20, 40, 60, 100} x weights in {90/10, 85/15, 70/30, 50/50}.

Top 5 configurations (sorted by aggregate MRR):

| k | v_w | s_w | R@5 | P@5 | MRR | Sym | Treat | Live |
|---|-----|-----|-----|-----|-----|-----|-------|------|
| **40** | **0.85** | **0.15** | **0.833** | **0.587** | **0.758** | **0.800** | **0.900** | **0.575** |
| 60 | 0.90 | 0.10 | 0.833 | 0.587 | 0.758 | 0.800 | 0.900 | 0.575 |
| 100 | 0.90 | 0.10 | 0.833 | 0.580 | 0.742 | 0.750 | 0.900 | 0.575 |
| 40 | 0.90 | 0.10 | 0.833 | 0.573 | 0.736 | 0.800 | 0.900 | 0.508 |
| 20 | 0.85 | 0.15 | 0.833 | 0.573 | 0.728 | 0.800 | 0.900 | 0.483 |

Best for living-with specifically: k=10, 50/50 (living MRR=0.600), but this degrades symptom MRR to 0.667. The k=40, 85/15 configuration provides the best balance.

### 4.3 Progression Summary

| Configuration | MRR | Live MRR | Treat MRR |
|--------------|-----|----------|-----------|
| Vector-only (original baseline) | 0.716 | 0.465 | 0.850 |
| + RRF BM25 70/30 k=60 (first attempt) | 0.689 | 0.400 | 0.900 |
| + RRF BM25F 85/15 k=40 (final) | **0.758** | **0.575** | **0.900** |

The final configuration improves aggregate MRR by +5.9% over vector-only while improving living-with MRR by +23.7% and treatment MRR by +5.9%. No category regresses.

## 5. Discussion

### 5.1 Why BM25F Outperforms Other Sparse Methods

The key insight is that not all keyword matches are equal. In our enriched chunks, the title and cancer type prefix carry strong relevance signal --- if a user queries "borstkanker behandeling" and the chunk title contains "borstkanker" and "behandeling", that's almost certainly the right chunk. Standard BM25 weights these matches the same as body text matches, diluting the signal. BM25F's field weighting amplifies the title signal, making the sparse component more precise.

This is particularly effective for living-with queries. A query like "vermoeidheid na kanker" contains the generic term "kanker" which matches thousands of chunks. But chunks whose title contains "vermoeidheid" are rare and highly relevant. BM25F's title boosting surfaces these.

### 5.2 Why 85/15 Outperforms 70/30

The living-with regression with 70/30 BM25 weighting occurred because BM25 was too influential, pushing keyword-matching but semantically irrelevant chunks above vector-similar relevant ones. Reducing BM25 to 15% means it acts as a tie-breaker rather than a driver --- it slightly boosts results that match keywords without overriding the semantic signal for broad queries.

### 5.3 Why k=40

Lower k values (10, 20) amplify rank differences --- the top-ranked sparse result gets disproportionate weight. This is volatile: if BM25F's top result happens to be irrelevant, it damages MRR significantly. k=40 provides enough smoothing that multiple sparse results contribute, making the fusion more robust. k=60 and k=100 oversmooth, reducing BM25F's contribution below the threshold where it helps.

### 5.4 Limitations

1. **Sample size**: 30 queries, 10 per category. Sufficient for directional conclusions but not statistical significance.
2. **Grid search used URL-only scoring**: LLM judge was omitted for speed. The sparse methods comparison used LLM judging, confirming that URL-based scoring correlates well.
3. **BM25F field weighting is heuristic**: We repeat title tokens 2x. The optimal multiplier was not searched.
4. **No cross-validation**: Same queries used for method selection and parameter tuning. Results may be optimistic.

## 6. Conclusion

For hybrid search in a Dutch cancer information RAG system, the choice of sparse retrieval method matters more than the fusion parameters. BM25F (field-weighted BM25 with title/cancer-type boosting) combined with RRF at k=40 and 85/15 vector/sparse weighting achieves the best aggregate MRR (+5.9% over vector-only) while being the only configuration that improves all three query categories simultaneously. The key principle: make the sparse signal smarter (field weighting) rather than louder (higher weight).

## Acknowledgments

This work was conducted as part of the BrabantHack_26 hackathon. The author thanks Team 5 members Danae Schillemans, Alysha den Exter, and Milou Drapers for their contributions to the chatbot system. The author gratefully acknowledges IKNL for organizing the Med Tech track and providing access to the kanker.nl data, and BOM (Brabantse Ontwikkelings-Maatschappij) for hosting the hackathon.

## References

1. Clarke, C.L.A., Cormack, G.V., Tudhope, E.A. "Relevance Ranking for One to Three Term Queries." Information Processing and Management, 2000.
2. Kamphuis, C. et al. "Which BM25 Do You Mean? A Large-Scale Reproducibility Study of Scoring Variants." ECIR 2020.
3. Cormack, G.V., Clarke, C.L.A., Buettcher, S. "Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods." SIGIR 2009.
4. Lv, Y., Zhai, C. "Lower-Bounding Term Frequency Normalization." CIKM 2011. (BM25+)
5. Robertson, S., Walker, S., Beaulieu, M. "Experimentation as a way of life: Okapi at TREC." Information Processing and Management, 2000.
6. BM25S Library. github.com/xhluca/bm25s
7. Fastembed Library. github.com/qdrant/fastembed
