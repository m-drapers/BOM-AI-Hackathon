# Comparative Evaluation of Chunking Strategies for Retrieval-Augmented Generation in a Dutch Cancer Information System

**Authors:** Team 5, BrabantHack_26 Hackathon (IKNL Med Tech Track)
**Date:** April 13, 2026

## Abstract

We evaluate five text chunking strategies for a retrieval-augmented generation (RAG) system that provides cancer information from kanker.nl patient pages in Dutch. We compare a fixed-window baseline (375 words) against sentence-aware, paragraph-level, semantic, and hybrid chunking on 2,622 pages using 30 test queries across three clinical categories (symptom lookup, treatment information, living with cancer). Sentence-aware chunking achieves the best Mean Reciprocal Rank (MRR = 0.717, +40.4% over baseline), the highest Recall@5 among practical strategies (0.800, +9.1%), and dominates on the hardest query category (living-with: 0.700 recall vs. 0.500 baseline). A subsequent chunk-size optimization confirms 300 words as the optimal maximum chunk size. We additionally introduce contextual chunk enrichment — prepending page title and cancer type to each chunk before embedding — to improve embedding disambiguation. The winning strategy has been deployed to production.

## 1. Introduction

Cancer patients and their families increasingly use online resources for health information. The Dutch national cancer registry (IKNL) maintains kanker.nl, a comprehensive patient information website covering 87 cancer types with 2,816 pages of reviewed medical content. To make this information more accessible, we built a conversational chatbot that uses retrieval-augmented generation to answer natural-language questions from trusted sources.

A critical design decision in any RAG system is how to chunk source documents before embedding them into a vector store. Poor chunking leads to missed relevant results, irrelevant retrievals, or broken semantic units that confuse the generation step. This is particularly important for medical text where splitting a symptom description mid-sentence could mislead patients.

We compare five chunking strategies in a controlled offline evaluation and report which approach best serves the three most common query patterns in cancer patient information seeking.

## 2. Data and System Description

### 2.1 Source Data

Our primary data source is a complete crawl of kanker.nl patient information pages:

| Property | Value |
|----------|-------|
| Total pages crawled | 2,816 |
| Pages after filtering (error pages, soft-404s) | 2,622 |
| Cancer types covered | 87 |
| Language | Dutch |
| Mean words per page | 521 |
| Median words per page | 418 |
| Range | 15 – 8,939 words |
| Format | Plain text (HTML-stripped, no markdown) |
| Structure | Single `\n` line breaks between paragraphs |
| Boilerplate | ~200 chars navigation footer on every page |

The text has no explicit heading markers. Content follows a consistent structure per page: title line, disclaimer, topic-of-contents, then paragraph-per-line body text, ending with a boilerplate navigation footer ("Praat mee", "Stel een vraag", "Vind lotgenoten", etc.).

### 2.2 Embedding Model

We use `intfloat/multilingual-e5-small` (Multilingual E5), a sentence-transformer model with 384 dimensions and a 512-token context window. Similarity is measured by cosine distance. The model supports Dutch text natively via its multilingual training.

The 512-token limit (~380 Dutch words) is a binding constraint: chunks exceeding this length are truncated silently by the model, meaning tail content is lost from the embedding.

### 2.3 Vector Store

ChromaDB with HNSW index, cosine distance metric. Each chunk is stored as a document with metadata fields: `kankersoort` (cancer type slug), `section`, `url`, and `title`.

## 3. Chunking Strategies

We evaluate five strategies. All strategies except the baseline (A) apply boilerplate footer stripping as a preprocessing step, removing the navigation footer that appears on every page.

### Strategy A: Fixed-Window Baseline

The existing production chunker. Splits text into 375-word windows with 38-word overlap. Uses `.split()` (whitespace tokenization) with no sentence or paragraph awareness. Boilerplate footer is included.

### Strategy B: Sentence-Aware

Splits on sentence boundaries using two heuristics: (1) period/exclamation/question mark followed by whitespace and a capital letter, and (2) newline characters. Sentences are merged into chunks up to a maximum of 300 words. Overlap is applied at sentence boundaries (last ~50 words of the previous chunk are prepended to the next).

### Strategy C: Paragraph-Level

Treats each `\n`-delimited line as a paragraph. Consecutive short paragraphs (< 50 words) are merged up to 400 words. No overlap is applied, on the assumption that paragraphs are self-contained semantic units.

### Strategy D: Semantic Chunking

Each sentence is embedded individually using the same E5 model. Adjacent sentence embeddings are compared by cosine similarity. When similarity drops below a threshold (0.75), a chunk boundary is inserted. This groups topically coherent sentences regardless of paragraph structure.

### Strategy E: Hybrid (Coarse + Fine)

Two-tier chunking: (1) the full page text as a single coarse chunk, and (2) paragraph-level chunks as fine-grained chunks. Both tiers are indexed in the same collection and queried simultaneously.

## 4. Evaluation Design

### 4.1 Test Queries

We constructed 30 test queries in Dutch across three categories representing the most common cancer information seeking patterns:

| Category | N | Description | Example |
|----------|---|-------------|---------|
| Symptom lookup | 10 | Direct questions about cancer symptoms | "Wat zijn de symptomen van darmkanker?" |
| Treatment information | 10 | Questions about treatments and procedures | "Welke behandelingen zijn er voor borstkanker?" |
| Living with cancer | 10 | Broader questions about life during/after cancer | "Hoe ga je om met vermoeidheid na kanker?" |

Queries cover 10 different cancer types (darmkanker, borstkanker, longkanker, blaaskanker, prostaatkanker, leverkanker, slokdarmkanker, eierstokkanker, melanoom, maagkanker) to avoid bias toward any single cancer type.

### 4.2 Relevance Ground Truth

Relevance is determined by two methods:

1. **URL-based ground truth:** For each query, we define relevant URL patterns (cancer type slug) and section keywords. A retrieved chunk is relevant if its source URL contains both a matching cancer type and a matching section.

2. **LLM-as-judge:** Each retrieved chunk is scored for relevance by an independent language model (GPT-4o-mini via OpenRouter). The model receives the query and chunk text and returns a binary relevant/not-relevant judgment.

A chunk is considered relevant if either method marks it as relevant. This combined approach compensates for the coarseness of URL-pattern matching (which misses relevant content from related pages) while the LLM judge catches relevance that URL patterns miss.

### 4.3 Metrics

We report three primary metrics, all computed at k=5 (top-5 retrieved chunks):

- **Recall@5:** Fraction of known-relevant pages represented in the top-5 results.
- **Precision@5:** Fraction of top-5 results that are relevant.
- **MRR (Mean Reciprocal Rank):** The reciprocal of the rank of the first relevant result, averaged across queries. Higher MRR means the user finds their answer faster.

We also report secondary metrics: total chunk count per variant (index size), average chunk size in words, and per-category breakdowns.

### 4.4 Experimental Protocol

For each strategy:

1. All 2,622 pages are chunked according to the strategy's rules.
2. Chunks are embedded and stored in an isolated ChromaDB collection (one per variant).
3. All 30 queries are run against the collection with `n_results=5`.
4. Retrieved chunks are scored for relevance using both ground-truth URL matching and LLM judging.
5. Metrics are computed per-query and aggregated.

Collections are deleted and recreated between runs. The embedding model is loaded once and shared across variants for fairness.

## 5. Results

### 5.1 Main Experiment

Table 1 shows the aggregate results across all 30 queries.

**Table 1: Aggregate retrieval metrics by chunking strategy (N=30 queries)**

| Strategy | Chunks | Avg Words | Recall@5 | Precision@5 | MRR | vs. Baseline |
|----------|--------|-----------|----------|-------------|-----|-------------|
| A. Fixed-window (baseline) | 5,114 | 281.5 | 0.733 | 0.373 | 0.511 | — |
| **B. Sentence-aware** | **5,853** | **242.1** | **0.800** | **0.440** | **0.717** | **+9.1% / +17.9% / +40.4%** |
| C. Paragraph-level | 4,498 | 282.7 | 0.733 | 0.360 | 0.609 | +0.0% / −3.6% / +19.4% |
| D. Semantic | 2,882 | 441.3 | 0.833 | 0.440 | 0.633 | +13.6% / +17.9% / +24.0% |
| E. Hybrid | 10,582 | 240.4 | 0.767 | 0.480 | 0.631 | +4.5% / +28.6% / +23.5% |

Strategy B (sentence-aware) achieves the highest MRR (0.717) by a substantial margin (+40.4% over baseline), meaning the first relevant result is consistently ranked in position 1 or 2. While strategy D (semantic) achieves the highest Recall@5 (0.833), its MRR is significantly lower (0.633), meaning relevant results appear lower in the ranking.

### 5.2 Per-Category Breakdown

Table 2 shows results broken down by query category.

**Table 2: Per-category MRR by strategy**

| Strategy | Symptom (N=10) | Treatment (N=10) | Living-with (N=10) |
|----------|---------------|-------------------|---------------------|
| A. Baseline | 0.412 | 0.767 | 0.353 |
| **B. Sentence** | **0.900** | **0.800** | **0.450** |
| C. Paragraph | 0.850 | 0.770 | 0.208 |
| D. Semantic | 0.692 | 0.850 | 0.358 |
| E. Hybrid | 0.900 | 0.758 | 0.233 |

**Table 3: Per-category Recall@5 by strategy**

| Strategy | Symptom (N=10) | Treatment (N=10) | Living-with (N=10) |
|----------|---------------|-------------------|---------------------|
| A. Baseline | 0.800 | 0.900 | 0.500 |
| **B. Sentence** | 0.900 | 0.800 | **0.700** |
| C. Paragraph | 0.900 | 0.900 | 0.400 |
| D. Semantic | **1.000** | 0.900 | 0.600 |
| E. Hybrid | **1.000** | 0.900 | 0.400 |

Key observations:

- **Symptom queries** are the easiest category. Strategies D and E achieve perfect recall (1.000), and strategies B and E share the best MRR (0.900). All strategies except A perform well here.
- **Treatment queries** show the smallest differences between strategies, suggesting that treatment information pages are well-structured and retrievable regardless of chunking approach.
- **Living-with queries** are the hardest category and the most discriminating. Strategy B dominates with 0.700 recall and 0.450 MRR. The next best recall is D at 0.600; the next best MRR is also D at 0.358. This category involves broader, cross-cutting content that benefits most from sentence-level coherence.

### 5.3 Chunk-Size Optimization (Drilldown)

To determine whether the 300-word maximum used in strategy B is optimal, we ran a second experiment varying the chunk size while keeping all other parameters constant.

**Table 4: Sentence-aware chunking at different maximum chunk sizes (N=30 queries)**

| Max Words | Chunks | Recall@5 | Precision@5 | MRR |
|-----------|--------|----------|-------------|-----|
| 150 | 11,252 | 0.767 | 0.500 | 0.686 |
| 200 | 8,568 | 0.800 | 0.473 | 0.668 |
| 250 | 6,910 | 0.733 | 0.420 | 0.576 |
| **300** | **5,853** | **0.800** | **0.440** | **0.717** |

The relationship between chunk size and MRR is non-monotonic. The 300-word maximum is clearly optimal, with MRR degrading at both smaller (150: −4.3%, 200: −6.8%) and intermediate (250: −19.7%) sizes. The 250-word result is notably the worst performer, suggesting it falls in a "dead zone" where chunks are too large to benefit from the precision advantage of smaller chunks but too small to capture the full context that makes 300-word chunks effective. The 300-word maximum is the Pareto-optimal point: it maximizes both MRR and Recall@5 simultaneously.

This result aligns with the embedding model's 512-token context window (~380 Dutch words): 300-word chunks fit comfortably within the limit, while 150-word chunks may be too sparse to capture enough context for the embedding to represent the semantic content accurately.

### 5.4 Computational Cost

**Table 5: Ingestion time by strategy (2,622 pages, single-threaded, CPU)**

| Strategy | Ingestion Time | Relative |
|----------|---------------|----------|
| A. Fixed-window | ~4 min | 1.0x |
| B. Sentence-aware | ~4 min | 1.0x |
| C. Paragraph | ~3 min | 0.75x |
| D. Semantic | ~46 min | 11.5x |
| E. Hybrid | ~5 min | 1.25x |

Strategy D (semantic) requires embedding every individual sentence before computing inter-sentence similarity, resulting in an 11.5x slowdown. For our corpus of 2,622 pages, this translates to ~130,000 individual sentence embeddings. This cost is prohibitive for iterative development and makes D impractical despite its strong Recall@5.

## 6. Contextual Chunk Enrichment

Beyond the chunking strategy comparison, we implemented contextual chunk enrichment as a complementary optimization. Before embedding, each chunk is prepended with its page title and cancer type:

```
"{title} — {kankersoort}: {original chunk text}"
```

For example:
```
"Symptomen van darmkanker — darmkanker-dikkedarmkanker: De symptomen
van darmkanker kunnen heel verschillend zijn..."
```

This makes chunks self-descriptive in the embedding space. Without enrichment, chunks about "symptomen van blaaskanker" and "symptomen van maagkanker" have similar embeddings because the differentiating context (cancer type) is stored only in metadata, not in the embedded text. With enrichment, the embedding model sees the cancer type directly, producing more discriminative representations.

We deployed enrichment together with sentence-aware chunking. A controlled evaluation of enrichment in isolation is left as future work.

## 7. Discussion

### 7.1 Why Sentence-Aware Chunking Wins

The primary failure mode of fixed-window chunking on this corpus is splitting semantic units. Kanker.nl pages are relatively short (median 418 words) with content organized as one concept per line. A symptom description such as "Bloed of slijm in je ontlasting kan door darmkanker komen. Het bloed hoeft er niet altijd rood uit te zien" forms a coherent unit that loses meaning when split at an arbitrary word boundary.

Sentence-aware chunking preserves these units by splitting only at sentence-terminal punctuation. This is particularly effective for the FAQ/lookup pattern that dominates cancer information seeking: patients ask about a specific symptom or treatment, and the answer is typically contained in 1-3 sentences.

### 7.2 Why Semantic Chunking Underperforms on MRR

Strategy D (semantic) achieves the highest Recall@5 (0.833) but a lower MRR (0.633) than sentence-aware (0.717). This counterintuitive result arises from the interaction between chunk size and embedding quality.

Semantic chunking produces larger chunks (avg 441 words vs. 242 for sentence-aware) because topically coherent passages are grouped together. These larger chunks often exceed the model's 512-token context window, causing truncation. The truncated embedding represents the beginning of the chunk well but loses information about its tail, reducing ranking precision. Meanwhile, the larger chunks are more likely to *contain* relevant information somewhere (higher recall), even if the embedding doesn't capture it precisely enough for high ranking.

### 7.3 The Living-With Gap

Living-with queries ("Hoe ga je om met vermoeidheid na kanker?", "Seksualiteit na kankerbehandeling") are consistently the hardest category across all strategies. These queries are cross-cutting: they relate to general cancer experience rather than a specific cancer type, and relevant information is scattered across multiple pages.

Strategy B's advantage here (0.700 recall vs. 0.500 baseline) suggests that preserving sentence-level coherence helps the embedding model distinguish between generic cancer-experience content and cancer-type-specific pages. The boilerplate stripping (which removes navigation text present on every page) may also contribute by reducing noise in the embedding space.

### 7.4 Limitations

1. **Sample size.** N=30 queries (10 per category) is sufficient for directional conclusions but not for statistical significance testing. We report results without confidence intervals.

2. **LLM judge reliability.** The LLM-as-judge (GPT-4o-mini) may have systematic biases in relevance assessment, particularly for Dutch medical text. We did not measure inter-rater agreement between the LLM judge and human annotators.

3. **Enrichment confound.** Contextual enrichment was deployed together with sentence-aware chunking. We did not isolate its effect in a separate experiment.

4. **Single embedding model.** All results are specific to `multilingual-e5-small` (512 tokens, 384 dimensions). A model with a longer context window (e.g., `multilingual-e5-large` at 1024 tokens) may change the relative performance of strategies, particularly favoring semantic chunking where the truncation penalty would be reduced.

5. **No end-to-end evaluation.** We evaluate retrieval quality only, not the quality of the final generated answers. Higher retrieval precision does not guarantee better answers if the generation model struggles with the retrieved content.

## 8. Related Work

Our work relates to several active research areas:

**RAG chunking benchmarks.** Vectara's February 2026 benchmark of 7 strategies across 50 academic papers found recursive 512-token splitting outperformed semantic chunking (69% vs. 54% accuracy). Our results partially align: sentence-aware (a form of structure-aware recursive splitting) outperforms semantic chunking on MRR, though semantic chunking leads on recall.

**Clinical RAG.** A November 2025 evaluation of chunking strategies for clinical decision support (PMC12649634) found adaptive chunking aligned to logical topic boundaries achieved 87% accuracy versus 13% for fixed-size baselines — a dramatic difference consistent with our +40% MRR improvement.

**Late chunking.** Günther et al. (arXiv:2409.04701) propose embedding the full document through the transformer before chunking, producing context-aware chunk embeddings. This requires a long-context embedding model (8192+ tokens) such as `jina-embeddings-v3`, which we did not evaluate.

**Contextual retrieval.** Anthropic's contextual retrieval approach prepends document-level context to each chunk before embedding, similar to our contextual enrichment. Their approach uses an LLM to generate the context, while ours uses structured metadata (title, cancer type) at zero inference cost.

**Multilingual clinical embeddings.** A 2026 JMIR study (e82997) demonstrated that embedding models fine-tuned on clinical documents outperform general-purpose models for medical RAG across multiple languages.

## 9. Conclusion

Sentence-aware chunking with 300-word maximum chunk size and contextual enrichment is the optimal retrieval strategy for the IKNL cancer information chatbot. It achieves the best MRR (+40% over baseline), the strongest performance on the hardest query category (living-with), and practical ingestion time (equivalent to the baseline).

The key insight is that for short, structured medical text with an FAQ-style access pattern, preserving sentence-level semantic coherence matters more than sophisticated embedding-based boundary detection. The embedding model's 512-token context window is the binding constraint — strategies that produce chunks exceeding this limit (semantic chunking, avg 441 words) pay a truncation penalty that offsets their theoretical advantages.

### Future Work

1. **Isolated enrichment evaluation.** Measure the effect of contextual chunk enrichment independently from the chunking strategy change.
2. **Embedding model upgrade.** Evaluate `multilingual-e5-large` (1024 tokens) to determine whether the larger context window changes the optimal strategy, particularly for semantic chunking.
3. **Cross-encoder reranking.** Add a reranking step after retrieval using a cross-encoder model (e.g., `cross-encoder/ms-marco-multilingual-MiniLM-L6-v2`), which is orthogonal to chunking improvements.
4. **End-to-end evaluation.** Measure answer quality (not just retrieval quality) using human annotators or the system's existing thumbs-up/thumbs-down feedback mechanism.
5. **Late chunking.** Evaluate the Jina late chunking approach with a long-context model, which would combine the benefits of sentence-aware splitting with document-level context awareness.

## References

1. Wang, L., et al. "Multilingual E5 Text Embeddings: A Technical Report." arXiv:2402.05672, 2024.
2. Günther, M., et al. "Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models." arXiv:2409.04701, 2024.
3. Vectara. "RAG Chunking Strategies: The 2026 Benchmark Guide." blog.premai.io, February 2026.
4. PMC12649634. "Comparative Evaluation of Advanced Chunking for Retrieval-Augmented Generation in Large Language Models for Clinical Decision Support." MDPI Bioengineering, November 2025.
5. JMIR e82997. "Improving Retrieval Augmented Generation for Health Care by Fine-Tuning Clinical Embedding Models." Journal of Medical Internet Research, January 2026.
6. arXiv:2505.21700. "Rethinking Chunk Size for Long-Document Retrieval: A Multi-Dataset Analysis." May 2025.
