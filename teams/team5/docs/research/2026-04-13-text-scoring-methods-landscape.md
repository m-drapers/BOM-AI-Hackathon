# Research Report: Text Corpus Scoring Methods — From TF-IDF to Cover Density

**Date:** 2026-04-13
**Context:** Before tuning RRF parameters, we need to understand the full landscape of sparse retrieval scoring methods to choose the right foundation. Current system uses basic BM25 via fastembed. This report maps the options.

## The Scoring Method Hierarchy

Text corpus scoring methods form a progression from simple to sophisticated. Each level adds a concept:

```
TF-IDF (1972)
  ↓ add term frequency saturation + length normalization
BM25 (1994)
  ↓ fix long-document bias
BM25+ / BM25L (2011)
  ↓ add field weighting
BM25F (structured documents)
  ↓ add term proximity
Cover Density Ranking (1999)
  ↓ add learned term importance
SPLADE / BM42 (2021+)
  ↓ parallel track: probabilistic language models
Dirichlet / Jelinek-Mercer LM
  ↓ parallel track: information-theoretic
Divergence from Randomness (DFR)
```

---

## 1. TF-IDF and Its Variants

The foundation. Score = how important is this term to this document relative to the corpus.

### Standard TF-IDF
```
score(t, d) = TF(t, d) × IDF(t)
TF(t, d) = count of term t in document d
IDF(t) = log(N / df(t))
```

### TF Variants (how to count term frequency)

| Variant | Formula | Effect |
|---------|---------|--------|
| **Raw** | `f(t,d)` | Linear — 100 occurrences = 10× more important than 10 |
| **Log-sublinear** | `1 + log(f(t,d))` | Diminishing returns — used by Lucene |
| **Augmented** | `0.5 + 0.5 × f(t,d) / max_f(d)` | Normalized by max term frequency in document |
| **Boolean** | `1 if f(t,d) > 0 else 0` | Presence only, ignores count |
| **Double normalization** | `K + (1-K) × f(t,d) / max_f(d)` | K typically 0.4, controls floor |

### IDF Variants

| Variant | Formula | Effect |
|---------|---------|--------|
| **Standard** | `log(N / df(t))` | Can be negative for very common terms |
| **Smooth** | `log(1 + N / df(t))` | Always positive |
| **Probabilistic** | `log((N - df(t)) / df(t))` | Used in BM25 IDF component |
| **BM25 IDF** | `log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)` | Smoothed, always positive |

**Relevance to our system:** TF-IDF is what we'd get if we disabled BM25's saturation and length normalization. It's strictly worse for retrieval but the IDF component is the key signal for query-dependent weight adaptation (Finding 2 from our RRF research).

---

## 2. BM25 Family

### BM25 (Okapi, 1994)
```
score(D, Q) = Σ IDF(qi) × [f(qi,D) × (k1 + 1)] / [f(qi,D) + k1 × (1 - b + b × |D|/avgdl)]
```

**Key parameters:**
- `k1 ∈ [1.2, 2.0]` — term frequency saturation. Higher = more weight to repeated terms.
- `b = 0.75` — document length normalization. 0 = ignore length, 1 = full normalization.

**What it adds over TF-IDF:** Saturation (diminishing returns for repeated terms) and length normalization (fair comparison across different document lengths).

### BM25+ (2011)
```
score(D, Q) = Σ IDF(qi) × [f(qi,D) × (k1 + 1) / (f(qi,D) + k1 × (1 - b + b × |D|/avgdl)) + δ]
```

**Extra parameter:** `δ = 1.0` — lower-bound bonus for matching documents.

**Problem solved:** Standard BM25 can score a long document that CONTAINS the query term similarly to a short document that DOESN'T contain it. BM25+ guarantees any matching document scores above any non-matching document of equal length.

**Relevance to us:** Our chunks range 50-300 words. Living-with content tends to be in longer chunks. BM25+ would stop these from being unfairly penalized. **This is the most relevant BM25 variant for our system.**

### BM25L (2011)
```
Modifies the TF normalization curve to be more stable for very long documents.
Uses: ctd = f(qi,D) / (1 - b + b × |D|/avgdl) → ctd' = ctd + δ
```

**Problem solved:** Same as BM25+ but approaches it differently. Smooths the entire normalization curve rather than adding a floor.

**Relevance:** Less relevant than BM25+ for our use case since our chunks are relatively short (max 300 words).

### BM25F (field-weighted)
```
Computes a weighted term frequency across document fields:
tf_weighted = Σ (w_field × tf_field) / (1 + b_field × (|field|/avg_field_len - 1))
```

**Problem solved:** Documents have structure — title, body, metadata. A term in the title should count more than the same term in the body.

**Relevance:** Interesting for us because our enriched chunks have a structure: `"{title} — {kankersoort}: {body text}"`. BM25F could weight the title/kankersoort portion higher than the body, giving more BM25 credit when query terms match the metadata prefix. **Worth exploring.**

### BM11 and BM15
Special cases: BM11 = BM25 with b=1 (full length normalization), BM15 = BM25 with b=0 (no length normalization). Useful as ablation benchmarks.

---

## 3. Cover Density Ranking (CDR)

A fundamentally different approach: instead of counting term frequency, CDR measures **how close together** query terms appear.

### Algorithm

**Step 1 — Coordination level:** Rank first by how many distinct query terms appear in the document. A doc with 3 of 3 query terms always ranks above a doc with 2 of 3.

**Step 2 — Cover scoring:** For documents at the same coordination level, find all "covers" — the shortest text spans containing all matched query terms.

### Scoring Formula
```
For cover set ω = {(p1,q1), (p2,q2), ..., (pn,qn)}:

S(ω) = Σ I(pj, qj)

where:
  I(pj, qj) = 1                      if qj - pj + 1 ≤ λ
  I(pj, qj) = λ / (qj - pj + 1)     otherwise
```

- `(pj, qj)` = start and end positions of the j-th cover (shortest span containing query terms)
- `λ = 16` (constant: covers shorter than 16 words get full score)

### How It Works (Example)

Query: "symptomen darmkanker"
Document: "...De **symptomen** van **darmkanker** kunnen heel verschillend zijn..."
- Cover: positions 3 to 5, length = 3 words
- Score contribution: 1.0 (length 3 < λ=16)

Document: "...**Symptomen** bij kankerbehandeling: vermoeidheid, misselijkheid... veel later... **darmkanker** informatie..."
- Cover: positions 1 to 47, length = 47 words
- Score contribution: 16/47 = 0.34

**The first document scores higher because the query terms are closer together.**

### Relevance to Our System

CDR is highly relevant for our use case:
- Our queries are typically 2-4 terms ("symptomen van darmkanker", "behandeling borstkanker")
- CDR would rank chunks where "symptomen" and "darmkanker" appear in the same sentence above chunks where they appear pages apart
- CDR is **complementary** to both BM25 and vector search — it measures something neither captures (term proximity)
- Could be used as a **third signal** in RRF alongside vector and BM25

**Implementation complexity:** Medium. Requires token-level positions (not just term counts). Need to build a positional index at ingestion time.

---

## 4. Probabilistic Language Models

An alternative framework to BM25: instead of scoring terms, estimate the probability that the document "generated" the query.

### Dirichlet Smoothing
```
P(w|d) = (f(w,d) + μ × P(w|C)) / (|d| + μ)
```
- `μ` = smoothing parameter (typically 2000)
- `P(w|C)` = probability of word w in the entire collection

**Adapts to document length automatically** — short documents get more smoothing from the collection model, long documents rely more on their own term frequencies.

### Jelinek-Mercer Smoothing
```
P(w|d) = (1-λ) × f(w,d)/|d| + λ × P(w|C)
```
- `λ ∈ [0, 1]` — interpolation weight (typically 0.1-0.7)

**Simpler but less adaptive** than Dirichlet. Length normalization is implicit.

### Relevance
For short queries on short documents (our exact use case), Dirichlet and BM25 typically perform similarly. The language model approach is more theoretically principled but harder to tune. **Not worth switching for our hackathon.**

---

## 5. Divergence from Randomness (DFR)

Scores based on how much a term's distribution in a document **diverges** from what you'd expect by random chance.

```
score(t, d) = -log2(Prob_random(tf >= observed_tf)) × (1 - Prob_collection(t))
```

**Key insight:** If a term appears in a document more than random chance would predict, it's likely relevant. DFR beats BM25 on short queries in some benchmarks.

**Relevance:** Promising for our 2-4 term queries but no readily available Python implementation for integration with ChromaDB. **Explore later.**

---

## 6. Learned Sparse Methods

### SPLADE
Uses a transformer to predict a sparse vector over the entire vocabulary for each document. Captures semantic expansion: "vermoeidheid" → also activates "moe", "energie", "uitgeput".

**Pros:** Handles vocabulary mismatch (our living-with problem). **Cons:** Requires trained model, high compute, limited multilingual support.

### BM42 (Qdrant)
Replaces BM25's term frequency with transformer attention weights. Keeps IDF. Fixes tokenization issues.

**Pros:** Better than BM25 for short texts. **Cons:** Qdrant-native, uncertain ChromaDB compatibility.

---

## Decision Matrix: Which Methods to Test

| Method | Effort | Expected Impact | Best For | Test? |
|--------|--------|----------------|----------|-------|
| **BM25 (current)** | Done | Baseline | — | Already tested |
| **BM25+** | Low (swap scoring method) | Medium — fixes living-with | Long-document bias | **Yes** |
| **BM25F** | Medium (field extraction) | Medium — better metadata matching | Structured chunks | **Yes** |
| **CDR** | Medium (positional index) | High — proximity signal | Multi-term queries | **Yes** |
| **BM25 + CDR hybrid** | Medium | High — combines frequency + proximity | All query types | **Yes** |
| Dirichlet LM | Medium | Low (similar to BM25 for our data) | Short queries | No |
| DFR | High (no library) | Unknown | Short queries | No |
| SPLADE | High (model training) | High but impractical | Vocabulary mismatch | No (hackathon) |

## Recommended Test Plan

**Before tuning RRF weights/k, test these sparse retrieval variants:**

1. **BM25 (current)** — baseline
2. **BM25+** — swap `fastembed` for `bm25s` with `method="bm25+"`
3. **BM25 + CDR** — add cover density as a third RRF signal
4. **BM25F** — weight title/kankersoort tokens higher than body tokens

Then the RRF parameter grid search operates on the **winning sparse method**, not just basic BM25.

## Sources

- [Which BM25 Do You Mean? (PMC7148026)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7148026/) — Large-scale BM25 variant comparison
- [BM25 Wikipedia](https://en.wikipedia.org/wiki/Okapi_BM25) — BM25, BM25+, BM25L, BM25F formulas
- [Cover Density Ranking (WWW 2002)](https://archives.iw3c2.org/www2002/CDROM/refereed/643/node7.html) — CDR algorithm and formula
- [Clarke et al. 1999](https://www.sciencedirect.com/science/article/abs/pii/S0306457399000175) — Original CDR paper for 1-3 term queries
- [BM25S Library](https://github.com/xhluca/bm25s) — BM25+, BM25L, ATIRE, Lucene variants in Python
- [SPLADE (Pinecone)](https://www.pinecone.io/learn/splade/) — Learned sparse retrieval
- [BM42 (Qdrant)](https://qdrant.tech/articles/bm42/) — Transformer-enhanced sparse retrieval
- [Language Models in Elasticsearch](https://www.elastic.co/blog/language-models-in-elasticsearch) — Dirichlet, Jelinek-Mercer smoothing
- [DFR (Wikipedia)](https://en.wikipedia.org/wiki/Divergence-from-randomness_model) — Divergence from Randomness model
- [Proximity Probabilistic Model (Microsoft)](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ppm.pdf) — BM25 + proximity extensions (+5-11% MAP)
