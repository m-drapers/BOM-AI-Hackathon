# Source Connectors -- Design Spec

> **Project:** Hackathon BOM-IKNL -- Cancer Information Chat System
> **Date:** 2026-04-10
> **Status:** Draft

---

## Overview

The chat system answers user questions about cancer by orchestrating multiple
data sources through a unified connector interface. Claude acts as the
reasoning layer: it reads the connector descriptions, decides which sources to
query, calls one or more connectors, and synthesises the results into a
coherent answer with proper citations.

Each connector is a self-contained module that knows how to reach one external
data source (vector store, REST API, file index). The connectors share a common
interface so that adding a new source requires no changes to the orchestration
layer.

---

## Common Interface

All connectors implement a single abstract contract.

```python
from dataclasses import dataclass, field
from typing import Any


class SourceConnector:
    name: str
    description: str  # Claude uses this to decide when to call it

    async def query(**params) -> "SourceResult":
        ...


@dataclass
class SourceResult:
    data: Any                    # structured data or text passages
    summary: str                 # human-readable for Claude to narrate
    sources: list["Citation"]    # URL + title + reliability indicator
    visualizable: bool           # hint to frontend for chart/map rendering


@dataclass
class Citation:
    url: str
    title: str
    reliability: str             # e.g. "official", "peer-reviewed", "scraped"
```

### Design decisions

| Decision | Rationale |
|---|---|
| `description` is a plain-language string | Claude selects connectors by reading these descriptions; structured routing would be more brittle. |
| `SourceResult.summary` is always populated | Even when returning structured data (tables, SIRs), the connector supplies a one-paragraph summary so Claude can narrate without guessing. |
| `visualizable` is a boolean hint | The frontend checks this flag before attempting chart or map rendering; connectors that return only prose set it to `False`. |
| `Citation.reliability` is a free string | Allows each connector to express trustworthiness in its own terms ("official registry", "peer-reviewed journal", "patient information website"). |

### Error handling

Every connector must catch its own transport and parsing errors and return a
`SourceResult` with an empty `data` field and a `summary` that explains the
failure in plain language, so Claude can relay the problem to the user instead
of crashing.

---

## kanker.nl Vector Search Connector

### Purpose

Provide semantic search over the patient-facing cancer information pages
published on kanker.nl (KWF Kankerbestrijding). This is the primary source for
general, non-statistical questions about cancer types, diagnosis, treatment, and
side effects.

### Data source

- **Input:** pre-crawled JSON file `data/kanker_nl_pages_all.json`.
- **Volume:** 2,816 pages spanning 88 cancer types.
- **Language:** Dutch.

### Sitemap construction

Parse the JSON into a hierarchical tree that mirrors the kanker.nl site
structure:

```
kankersoort (e.g. borstkanker)
 +-- section (algemeen | diagnose | onderzoeken | behandelingen | gevolgen | na-de-uitslag)
      +-- page (individual article)
```

Persist the result as `sitemap.json` with the following per-node fields:

| Field | Type | Description |
|---|---|---|
| `kankersoort` | `str` | Cancer type slug (e.g. `borstkanker`) |
| `section` | `str` | One of the six canonical sections |
| `url` | `str` | Full canonical URL on kanker.nl |
| `title` | `str` | Page title |
| `metadata` | `dict` | Any extra attributes extracted from the crawl |

### Data cleaning

1. **Error pages:** exclude the 2 pages that returned HTTP 503 during the
   crawl.
2. **Duplicate slugs:** deduplicate the ~18 overlapping URL slugs (keep the
   version with the most content).
3. **URL normalisation:** strip trailing slashes and enforce a single
   `https://www.kanker.nl/` prefix.

### Vector ingestion pipeline

1. Split each page body into chunks of approximately **500 tokens** with a
   **50-token overlap** to preserve sentence boundaries across chunk edges.
2. Attach metadata to every chunk:
   - `kankersoort`
   - `section`
   - `url`
   - `title`
3. Compute embeddings using a **multilingual model**. Two candidates:
   - `text-embedding-3-small` (OpenAI) -- lower latency, hosted.
   - `multilingual-e5-large` (local) -- better Dutch-language recall, no
     external dependency.
   Decision: prefer the local model for Dutch content accuracy; fall back to
   the OpenAI model if GPU memory is unavailable on the hackathon machine.
4. Store embeddings in **ChromaDB** (persistent, file-based storage in
   `data/chromadb/`). Collection name: `kanker_nl`.

### Retrieval strategy

**Filter-aware retrieval.** When the user's question contains identifiable
entities, the connector applies metadata filters *before* similarity search.
This dramatically reduces the search space and improves precision.

Example: a question about "borstkanker behandeling" results in:

```python
collection.query(
    query_texts=[user_query],
    where={"$and": [
        {"kankersoort": {"$eq": "borstkanker"}},
        {"section": {"$eq": "behandelingen"}},
    ]},
    n_results=5,
)
```

When no entities can be extracted, the connector falls back to unfiltered
top-k similarity search.

### Tool definition

```
search_kanker_nl(
    query: str,                  # free-text search query
    kankersoort: str | None,     # optional cancer type filter
    section: str | None,         # optional section filter
) -> SourceResult
```

Claude receives the following description:

> "Search the kanker.nl patient information database for general information
> about cancer types, diagnosis, treatment options, side effects, and life
> after diagnosis. Content is in Dutch. Optionally filter by cancer type
> (kankersoort) and section."

---

## NKR-Cijfers API Connector

### Purpose

Provide access to the Netherlands Cancer Registry (NKR) statistics: incidence,
prevalence, mortality, survival, stage distribution, and conditional survival.
This is the authoritative source for epidemiological data.

### API surface

- **Base URL:** `https://api.nkr-cijfers.iknl.nl/api/`
- **Protocol:** all endpoints accept `POST` with JSON bodies.

| Endpoint | Purpose |
|---|---|
| `/navigation-items` | Hierarchical tree of ~200 cancer types |
| `/configuration` | Available data pages and their settings |
| `/filter-groups` | Filter definitions for a given data page |
| `/data` | Actual statistical data |

### Data pages (6)

1. Incidence (new cases per year)
2. Stage distribution (TNM staging breakdown)
3. Prevalence (living patients)
4. Mortality (deaths per year)
5. Survival from diagnosis (1-/5-/10-year)
6. Conditional survival (survival given already survived N years)

### Available filters

| Filter | Values |
|---|---|
| Period | 1961 -- 2025 |
| Sex | Male, Female, Both |
| Age group | 0-14, 15-29, 30-44, 45-59, 60-74, 75+, All |
| Region | 12 Dutch provinces + national |
| Stage | I, II, III, IV, Unknown, All |

### Caching strategy

The navigation items and filter-group definitions are **static data** that
change only when IKNL updates the registry. Cache these at application startup
and refresh once per session. This eliminates redundant round-trips and makes
Claude's filter resolution instantaneous.

### Important: body format divergence

The `/data` endpoint uses a **different JSON body structure** than
`/filter-groups`. Key differences:

| Aspect | `/filter-groups` | `/data` |
|---|---|---|
| Navigation key | `currentNavigation` | `navigation` |
| Grouping | not applicable | `groupBy` / `aggregateBy` structure |

Mixing these formats produces silent 200 responses with empty data.
The connector must maintain separate body builders for each endpoint.

### Tool definitions

```
get_cancer_incidence(
    cancer_type: str,            # cancer type name or code
    period: str,                 # year or range (e.g. "2020" or "2015-2020")
    sex: str | None,             # male / female / both
    age_group: str | None,       # e.g. "60-74"
    region: str | None,          # Dutch province name or "national"
) -> SourceResult

get_survival_rates(
    cancer_type: str,
    period: str,
    sex: str | None,
    age_group: str | None,
) -> SourceResult

get_stage_distribution(
    cancer_type: str,
    period: str,
    sex: str | None,
) -> SourceResult
```

All three tools set `visualizable = True` on the returned `SourceResult` so
the frontend can render charts.

Claude receives the following description for the incidence tool:

> "Query the Netherlands Cancer Registry for incidence (new cases) data.
> Returns counts and rates per 100,000 for the requested cancer type, period,
> and optional demographic filters. Data is authoritative and covers 1961 to
> present."

---

## Cancer Atlas Connector

### Purpose

Provide geographic variation data for cancer incidence across the Netherlands
at postcode level. Useful for answering questions like "Is cancer X more common
in my region?" and for rendering choropleth maps.

### API surface

Two REST backends:

| Host | Role |
|---|---|
| `kankeratlas.iknl.nl` | Public-facing map application |
| `iknl-atlas-strapi-prod.azurewebsites.net` | CMS / content API (Strapi) |

### Data model

- **Cancer groups:** 25 groups, each identified by a numeric ID.
- **Sex validity:** each group carries a `validsex` flag:
  - `1` = men only
  - `2` = women only
  - `3` = both sexes
- **Geographic granularity:**
  - **PC3** (3-digit postcode) -- ~890 areas. Available for all cancer groups.
  - **PC4** (4-digit postcode) -- available for lung cancer only (higher
    volume enables finer resolution).
- **Metric:** Standardized Incidence Ratios (SIRs) with Bayesian posterior
  distribution percentiles (p10, p25, p50, p75, p90) and a credibility score.

### Internal mapping

The connector maintains a lookup table from human-readable cancer group names
(Dutch) to numeric IDs, so Claude never needs to know the IDs.

### Tool definition

```
get_regional_cancer_data(
    cancer_type: str,            # cancer group name (Dutch)
    sex: str | None,             # male / female / both
    postcode: str | None,        # 3- or 4-digit postcode prefix
) -> SourceResult
```

When a postcode is provided, the connector returns the SIR and credibility
interval for that specific area. When omitted, it returns a national summary
with top-5 highest and lowest areas. Both modes set `visualizable = True`.

Claude receives the following description:

> "Look up regional cancer incidence data from the IKNL Cancer Atlas. Returns
> Standardized Incidence Ratios (SIRs) at postcode level for 25 cancer groups,
> showing whether a region has higher or lower incidence than the national
> average. Can render as a map."

---

## Publications/Reports Connector

### Purpose

Provide semantic search over scientific publications and institutional reports
that contain deeper analysis than the registry statistics or patient
information pages. Useful for evidence-based clinical context and research
findings.

### Data sources

Extracted at startup using **PyMuPDF** (`fitz`).

#### Dutch reports (3)

| Title | Topic |
|---|---|
| Gender differences in cancer | Sex-specific incidence and outcome patterns |
| Metastatic cancer 2025 | Current state of metastatic disease in NL |
| Colorectal trends | Long-term trends in colorectal cancer |

#### English papers (2)

| Title | Venue | Topic |
|---|---|---|
| Comorbidities and survival in 8 cancers | The Lancet | Impact of comorbid conditions on cancer survival |
| Ovarian cancer ML prediction | ESMO | Machine learning model for ovarian cancer outcomes |

### Ingestion pipeline

1. Extract full text from each PDF using PyMuPDF.
2. Chunk into ~500-token segments with 50-token overlap (same strategy as
   kanker.nl connector).
3. Attach metadata per chunk:
   - `source_type`: `"report"` or `"publication"`
   - `title`: document title
   - `language`: `"nl"` or `"en"`
   - `topic`: short topic descriptor
4. Embed and store in ChromaDB in a **separate collection**: `publications`.

### Tool definition

```
search_publications(
    query: str,                  # free-text search query
    source_type: str | None,     # "report" or "publication"
    language: str | None,        # "nl" or "en"
) -> SourceResult
```

Claude receives the following description:

> "Search indexed scientific publications and institutional reports about
> cancer. Includes Lancet and ESMO papers (English) and IKNL reports on
> gender differences, metastatic cancer, and colorectal trends (Dutch).
> Filter by source type or language."

---

## Richtlijnendatabase Connector (Stretch Goal)

### Purpose

Provide access to Dutch clinical oncology guidelines from richtlijnendatabase.nl.
These guidelines define the standard of care and are the most authoritative
source for treatment protocol questions.

### Constraints

- **No public API.** Content must be scraped.
- Scraping is done as a **pre-processing step** during setup, not at query
  time (to stay within acceptable load and avoid blocking the chat).

### Approach

1. **Pre-scrape** the most common oncology guidelines during application
   setup. Priority list:
   - Prostaatcarcinoom
   - Mammacarcinoom (borstkanker)
   - Colorectaal carcinoom
   - Longcarcinoom
   - Melanoom
   - Blaascarcinoom
   Example URL: `https://richtlijnendatabase.nl/richtlijn/prostaatcarcinoom/`
2. Extract and clean HTML content (strip navigation, footers, sidebars).
3. Chunk and embed into a **third ChromaDB collection**: `guidelines`.
4. Attach metadata: `cancer_type`, `guideline_section`, `url`.

### Fallback behaviour

If the user asks about a guideline that has not been pre-indexed, the
connector returns a `SourceResult` with:
- `data`: `None`
- `summary`: a message explaining the guideline was not pre-indexed
- `sources`: a single `Citation` with the expected URL on
  richtlijnendatabase.nl so Claude can direct the user there
- `visualizable`: `False`

### Tool definition

```
search_guidelines(
    query: str,                  # free-text search query
    cancer_type: str | None,     # optional cancer type filter
) -> SourceResult
```

Claude receives the following description:

> "Search Dutch clinical oncology guidelines from richtlijnendatabase.nl.
> Contains evidence-based treatment protocols and diagnostic recommendations.
> NOTE: only a subset of guidelines has been pre-indexed; for missing
> guidelines a direct URL is returned."

---

## ChromaDB Collection Layout

All vector data lives under `data/chromadb/` with three collections:

| Collection | Source | Approx. chunks | Metadata keys |
|---|---|---|---|
| `kanker_nl` | kanker.nl pages | ~15,000 | kankersoort, section, url, title |
| `publications` | PDFs (reports + papers) | ~2,000 | source_type, title, language, topic |
| `guidelines` | richtlijnendatabase.nl | ~5,000 (stretch) | cancer_type, guideline_section, url |

All collections use the same embedding model to ensure queries can be run
cross-collection when needed.

---

## Connector Selection Flow

When Claude receives a user question, the orchestration layer presents all
connector descriptions. Claude then:

1. **Analyses intent:** informational, statistical, geographic, clinical.
2. **Selects connectors:** may call multiple connectors in parallel (e.g.
   `search_kanker_nl` + `get_cancer_incidence` for "how common is lung cancer
   and what are the symptoms?").
3. **Merges results:** reads each `SourceResult.summary`, reconciles any
   contradictions, and composes a single answer.
4. **Cites sources:** includes URLs from `SourceResult.sources` in the
   response.
5. **Signals visualisation:** if any result has `visualizable = True`, tells
   the frontend to render the appropriate chart or map.

---

## Open Questions

- **Embedding model final choice:** benchmark `text-embedding-3-small` vs
  `multilingual-e5-large` on a set of 50 Dutch cancer queries before the demo.
- **Rate limiting on NKR-Cijfers API:** unclear if there are request-per-minute
  limits; the connector should implement exponential backoff as a precaution.
- **Richtlijnendatabase scraping legality:** confirm with IKNL legal/comms
  whether pre-scraping for a hackathon demo is acceptable.
- **Cross-collection search:** should Claude be able to search all three
  ChromaDB collections in a single call, or always pick one?
