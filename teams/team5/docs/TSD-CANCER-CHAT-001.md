# TSD-CANCER-CHAT-001: Cancer Information Chat System

## Document Info

| Field | Value |
|-------|-------|
| TSD ID | TSD-CANCER-CHAT-001 |
| PRD Reference | PRD-CANCER-CHAT-001 |
| Status | Draft |
| Author | Team 5 |
| Created | 2026-04-10 |
| Classification | Hackathon Prototype |

---

## 1. Technical Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 14.x |
| UI Framework | Tailwind CSS | 3.x |
| Charts | Recharts | 2.x |
| Language | TypeScript | 5.x |
| Backend | FastAPI | 0.110+ |
| Python | Python | 3.11+ |
| LLM Primary | Anthropic Claude | claude-sonnet-4-20250514 |
| LLM Abstraction | LiteLLM | latest |
| LLM Fallback | Ollama | latest |
| Vector Store | ChromaDB | 0.5+ |
| Embeddings | multilingual-e5-large / text-embedding-3-small | - |
| PDF Extraction | PyMuPDF (fitz) | latest |
| Feedback DB | SQLite | 3 |
| Package Mgmt (Python) | uv | latest |
| Package Mgmt (Node) | pnpm | 9.x |
| Containerization | Docker Compose | 3.x |

### 1.1 Stack Rationale

- **Next.js 14 App Router** -- server components and native streaming support align with the SSE-based chat architecture. App Router keeps the frontend thin and avoids over-engineering.
- **Tailwind CSS** -- enables rapid prototyping during the hackathon while producing a clean, responsive UI without custom CSS files.
- **Recharts** -- lightweight React-native charting library covering bar and line charts for NKR-Cijfers data without the complexity of D3 or Highcharts.
- **FastAPI with async** -- native SSE support, automatic OpenAPI docs for demo purposes, and excellent performance for streaming LLM responses.
- **Claude native tool-use** -- avoids LangChain/LangGraph overhead. The orchestrator passes tool definitions to Claude; Claude decides which connectors to invoke. Simple and debuggable.
- **LiteLLM** -- provider-agnostic abstraction so the LLM can be swapped from Claude to Ollama without code changes, providing demo resilience.
- **ChromaDB (file-based)** -- zero infrastructure, persistent directory in `data/chromadb/`, survives restarts.
- **SQLite** -- same zero-infrastructure principle for feedback storage. Single `.db` file, no server process.
- **uv + pnpm** -- fast, modern package managers that reduce install times during hackathon setup.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    Next.js Frontend                       │
│   Chat UI (streaming) | Source Cards | Data Viz (charts)  │
└─────────────────────────┬────────────────────────────────┘
                          │ SSE / streaming
┌─────────────────────────┴────────────────────────────────┐
│                 FastAPI Backend                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │             Chat Orchestrator                     │    │
│  │  - User profiling (stakeholder type + intent)     │    │
│  │  - Claude native tool-use (primary)               │    │
│  │  - LiteLLM provider abstraction (Ollama fallback) │    │
│  └───────┬──────────┬──────────┬──────────┬─────────┘    │
│          │          │          │          │               │
│  ┌───────┴──┐ ┌─────┴───┐ ┌───┴───┐ ┌───┴──────────┐   │
│  │kanker.nl │ │NKR-Cijf.│ │ Atlas │ │Publications  │   │
│  │ Vector   │ │  API    │ │  API  │ │ PDF/Text     │   │
│  │ Search   │ │Connector│ │ Conn. │ │ Search       │   │
│  └───────┬──┘ └─────────┘ └───────┘ └──────────────┘   │
│          │                                               │
│  ┌───────┴─────────────┐                                 │
│  │  ChromaDB (vector)  │                                 │
│  └─────────────────────┘                                 │
└──────────────────────────────────────────────────────────┘
```

### 2.1 Key Architectural Decisions

**Claude native tool-use instead of an orchestration framework.** Claude's built-in tool-use handles both simple single-source lookups and complex multi-source queries without an external framework. Each data source connector is registered as a Claude tool. Claude decides which tools to call based on the user query and the profile context injected into the system prompt.

**Multi-source synthesis via sequential tool calls.** For complex queries (e.g., "What are survival rates for stage III colorectal cancer in Noord-Brabant compared to the national average, and what does kanker.nl say about treatment?"), Claude calls multiple tools in sequence: NKR-Cijfers for statistics, Cancer Atlas for regional breakdown, kanker.nl for patient-facing treatment information. It synthesizes the combined results into a single coherent response with per-claim citations.

**SSE streaming from backend to frontend.** The FastAPI backend streams responses token-by-token to the Next.js frontend via Server-Sent Events, so users see answers appearing in real time rather than waiting for the full response to complete.

**Ingestion is a separate pipeline.** The `ingestion/` directory contains scripts that run once at setup to build the vector store. They are not part of the request path. All retrieval happens against pre-built indexes, keeping chat response times fast.

---

## 3. Project Structure

```
├── backend/
│   ├── main.py                 # FastAPI app, SSE endpoint, CORS, startup hooks
│   ├── orchestrator.py         # Chat orchestrator, Claude tool-use, profile routing
│   ├── connectors/
│   │   ├── base.py             # SourceConnector interface, SourceResult, Citation
│   │   ├── kanker_nl.py        # Vector search over kanker.nl content
│   │   ├── nkr_cijfers.py      # NKR-Cijfers REST API wrapper
│   │   ├── cancer_atlas.py     # Cancer Atlas API wrapper (Strapi + filters)
│   │   ├── publications.py     # PDF/report vector search
│   │   └── richtlijnen.py      # Richtlijnendatabase search (stretch goal)
│   ├── ingestion/
│   │   ├── sitemap_builder.py  # kanker.nl JSON → hierarchical sitemap tree
│   │   ├── vectorize.py        # Chunking + embedding + ChromaDB storage
│   │   └── pdf_extractor.py    # PDF text extraction via PyMuPDF
│   ├── models.py               # Pydantic models (request/response/session/feedback)
│   └── config.py               # Settings, API keys, provider config, env vars
├── frontend/
│   ├── app/
│   │   ├── page.tsx            # Main chat page
│   │   └── api/                # Optional BFF routes (CORS proxy if needed)
│   ├── components/
│   │   ├── ChatMessage.tsx     # Message bubble with Markdown + inline charts
│   │   ├── SourceCard.tsx      # Collapsible source citation cards
│   │   ├── DataChart.tsx       # Recharts wrapper (line, bar, value types)
│   │   ├── FeedbackWidget.tsx  # Thumbs up/down + "Informatie mist?" input
│   │   └── ProfileSelector.tsx # Patient / Professional / Policymaker selector
│   └── lib/
│       └── chat-client.ts      # SSE streaming client with reconnection logic
├── data/
│   ├── kanker_nl_pages_all.json  # Pre-crawled kanker.nl content (2,816 pages)
│   ├── publications/             # PDF reports and papers
│   ├── chromadb/                 # Persistent ChromaDB vector store
│   └── feedback.db              # SQLite feedback database
├── docs/
│   ├── 60-prd/
│   ├── 61-tsd/
│   └── success-criteria.md
└── docker-compose.yml
```

---

## 4. API Specification

### 4.1 Backend Endpoints

#### POST /api/chat/stream

SSE streaming chat endpoint. Opens a server-sent event connection and streams the assistant's response incrementally.

**Request body:**

```json
{
  "message": "Hoe vaak komt borstkanker voor bij vrouwen?",
  "session_id": "uuid-v4",
  "profile": "patient",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | yes | The user's current question |
| `session_id` | `string` | yes | UUID identifying the chat session |
| `profile` | `"patient" \| "professional" \| "policymaker"` | yes | Active user profile for tone/source adaptation |
| `history` | `Message[]` | no | Previous messages for conversational context |

**SSE event types:**

| Event | Data | Description |
|-------|------|-------------|
| `token` | `{ "text": "..." }` | Single token or token batch for streaming display |
| `source_card` | `{ "source": "...", "url": "...", "reliability": "...", "contributed": true }` | Source citation card metadata |
| `chart_data` | `{ "type": "line\|bar\|value", "title": "...", "data": [...], "x_key": "...", "y_key": "..." }` | Structured chart data for inline visualization |
| `done` | `{ "message_id": "uuid", "sources_tried": ["..."] }` | Stream completion signal with metadata |
| `error` | `{ "code": "...", "message": "..." }` | Error event if processing fails |

**Response headers:**

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

#### POST /api/feedback

Submit user feedback on a specific assistant response.

**Request body:**

```json
{
  "session_id": "uuid-v4",
  "message_id": "uuid-v4",
  "rating": "positive",
  "comment": "Ik miste informatie over bijwerkingen.",
  "query": "Wat zijn de behandelingen voor borstkanker?",
  "sources_tried": ["kanker_nl", "nkr_cijfers"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | `string` | yes | Session identifier |
| `message_id` | `string` | yes | Message being rated |
| `rating` | `"positive" \| "negative"` | yes | Thumbs up or down |
| `comment` | `string` | no | Free-text explanation of missing information |
| `query` | `string` | yes | The original user query that produced this response |
| `sources_tried` | `string[]` | yes | List of connector names that were queried |

**Response:** `201 Created` with `{ "id": "feedback-uuid" }`

#### GET /api/feedback/export

Export all feedback entries as CSV for post-hackathon analysis by IKNL.

**Response:** `200 OK` with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="feedback-export.csv"`

**CSV columns:** `id, session_id, message_id, rating, comment, query, sources_tried, profile, timestamp`

#### GET /api/health

Health check endpoint for Docker Compose and monitoring.

**Response:**

```json
{
  "status": "healthy",
  "llm_provider": "anthropic",
  "chromadb_collections": ["kanker_nl", "publications"],
  "version": "0.1.0"
}
```

### 4.2 External API Integration

#### NKR-Cijfers API

- **Base URL:** `https://api.nkr-cijfers.iknl.nl/api/`
- **Protocol:** All endpoints accept `POST` with JSON bodies.

| Endpoint | Purpose |
|----------|---------|
| `/navigation-items` | Hierarchical tree of ~200 cancer types |
| `/configuration` | Available data pages and their settings |
| `/filter-groups` | Filter definitions for a given data page |
| `/data` | Actual statistical data (incidence, survival, etc.) |

**Critical implementation detail:** The `/data` endpoint and `/filter-groups` endpoint use different JSON body structures. The `/data` endpoint uses a `navigation` key, while `/filter-groups` uses `currentNavigation`. Mixing these formats produces silent 200 responses with empty data arrays. The connector must maintain separate request body builders for each endpoint.

**Data pages (6):** Incidence, Stage distribution, Prevalence, Mortality, Survival from diagnosis, Conditional survival.

**Available filters:** Period (1961--2025), Sex (Male/Female/Both), Age group (0-14, 15-29, 30-44, 45-59, 60-74, 75+, All), Region (12 Dutch provinces + national), Stage (I, II, III, IV, Unknown, All).

**Cache strategy:** Navigation items and filter-group definitions are static data that change only when IKNL updates the registry. Cache at application startup and refresh once per session. This eliminates redundant round-trips and makes Claude's filter resolution instantaneous.

#### Cancer Atlas API

Two separate backends:

| Host | Role |
|------|------|
| `kankeratlas.iknl.nl` | Public-facing map application |
| `iknl-atlas-strapi-prod.azurewebsites.net` | CMS / content API (Strapi) |

**Endpoints:**

| Method | URL | Purpose |
|--------|-----|---------|
| GET | `https://kankeratlas.iknl.nl/locales/nl/filters.json` | Available filters and cancer groups |
| GET | `https://iknl-atlas-strapi-prod.azurewebsites.net/api/cancer-groups/cancergrppc` | Cancer group definitions with valid sex flags |
| GET | `https://iknl-atlas-strapi-prod.azurewebsites.net/api/cancer-datas/getbygroupsexpostcode/{group}/{sex}/{pc}` | SIR data for a specific cancer group, sex, and postcode |

**Data model:** 25 cancer groups identified by numeric ID. Each group carries a `validsex` flag (1=men only, 2=women only, 3=both). Geographic granularity is PC3 (3-digit postcode, ~890 areas) for all groups, and PC4 (4-digit postcode) for lung cancer only. Metric is Standardized Incidence Ratios (SIRs) with Bayesian posterior distribution percentiles (p10, p25, p50, p75, p90) and a credibility score.

---

## 5. Data Models

### 5.1 Backend Models (Pydantic)

```python
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage] = []


class Citation(BaseModel):
    url: str
    title: str
    reliability: str  # "official", "peer-reviewed", "patient-info", "scraped"


class SourceCard(BaseModel):
    source: str       # connector name (kanker_nl, nkr_cijfers, etc.)
    url: str          # deep link to the specific content
    reliability: str  # reliability badge text
    contributed: bool # whether it contributed content to the response


class ChartData(BaseModel):
    type: Literal["line", "bar", "value"]
    title: str
    data: list[dict]  # Recharts-compatible data array
    x_key: str
    y_key: str
    unit: Optional[str] = None


class FeedbackEntry(BaseModel):
    session_id: str
    message_id: str
    rating: Literal["positive", "negative"]
    comment: Optional[str] = None
    query: str
    sources_tried: list[str]
    profile: Optional[str] = None
    timestamp: datetime = None


class SourceResult(BaseModel):
    """Returned by every connector after a query."""
    data: dict | list | str | None
    summary: str        # human-readable for Claude to narrate
    sources: list[Citation]
    visualizable: bool  # hint to frontend for chart rendering


class SessionContext(BaseModel):
    """Internal state tracked per chat session."""
    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage]
    inferred_intent: Optional[str] = None  # informational, statistical, geographic, clinical
```

### 5.2 Connector Interface

```python
from abc import ABC, abstractmethod


class SourceConnector(ABC):
    name: str
    description: str  # Claude reads this to decide when to call the connector

    @abstractmethod
    async def query(self, **params) -> SourceResult:
        """Execute a query against this data source."""
        ...
```

All connectors must catch their own transport and parsing errors and return a `SourceResult` with an empty `data` field and a `summary` explaining the failure in plain language, so Claude can relay the problem to the user instead of crashing.

### 5.3 Frontend Types (TypeScript)

```typescript
interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  id?: string;
  sourceCards?: SourceCard[];
  chartData?: ChartData[];
}

interface SourceCard {
  source: string;
  url: string;
  reliability: string;
  contributed: boolean;
}

interface ChartData {
  type: "line" | "bar" | "value";
  title: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  unit?: string;
}

type UserProfile = "patient" | "professional" | "policymaker";

interface ChatRequest {
  message: string;
  session_id: string;
  profile: UserProfile;
  history: ChatMessage[];
}
```

---

## 6. Vector Store Schema

### 6.1 ChromaDB Collections

All vector data is stored under `data/chromadb/` in three persistent collections:

| Collection | Source | Est. Chunks | Metadata Fields |
|------------|--------|-------------|-----------------|
| `kanker_nl` | kanker.nl pages (2,816 pages, 88 cancer types) | ~15,000 | `kankersoort`, `section`, `url`, `title` |
| `publications` | PDF reports and papers (5 documents) | ~2,000 | `source_type`, `title`, `language`, `topic` |
| `guidelines` | richtlijnendatabase.nl (stretch goal) | ~5,000 | `cancer_type`, `guideline_section`, `url` |

### 6.2 Embedding Configuration

- **Primary model:** `multilingual-e5-large` (local, via sentence-transformers) -- better Dutch-language recall, no external dependency.
- **Fallback model:** `text-embedding-3-small` (OpenAI hosted) -- lower latency, used if GPU memory is unavailable on the hackathon machine.
- **Chunk size:** ~500 tokens with 50-token overlap to preserve sentence boundaries across chunk edges.
- **Distance metric:** cosine similarity.

All collections use the same embedding model to ensure queries can be run cross-collection when needed.

### 6.3 Retrieval Strategy

**Filter-aware retrieval.** When the user's question contains identifiable entities, the connector applies metadata filters before similarity search, reducing the search space and improving precision.

Example for "borstkanker behandeling":

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

When no entities can be extracted, the connector falls back to unfiltered top-k similarity search with `n_results=5`.

---

## 7. Ingestion Pipeline

### 7.1 kanker.nl Content

1. **Parse:** Read `data/kanker_nl_pages_all.json` and build hierarchical sitemap tree mirroring the kanker.nl site structure: `kankersoort > section > page`.
2. **Clean:** Exclude 2 pages with HTTP 503 errors. Deduplicate ~18 overlapping URL slugs (keep the version with most content). Normalize URLs to `https://www.kanker.nl/` prefix, strip trailing slashes.
3. **Chunk:** Split each page body into ~500-token chunks with 50-token overlap.
4. **Embed:** Compute embeddings using the selected multilingual model.
5. **Store:** Write to ChromaDB collection `kanker_nl` with metadata: `kankersoort`, `section`, `url`, `title`.

### 7.2 Publications and Reports

1. **Extract:** Use PyMuPDF (`fitz`) to extract full text from each PDF in `data/publications/`.
2. **Chunk:** Split into ~500-token segments with 50-token overlap.
3. **Tag:** Attach metadata per chunk: `source_type` ("report" or "publication"), `title`, `language` ("nl" or "en"), `topic`.
4. **Embed and store:** Write to ChromaDB collection `publications`.

**Source documents:**

| Title | Language | Type | Topic |
|-------|----------|------|-------|
| Gender differences in cancer | NL | report | Sex-specific incidence and outcome patterns |
| Metastatic cancer 2025 | NL | report | Current state of metastatic disease in NL |
| Colorectal trends | NL | report | Long-term trends in colorectal cancer |
| Comorbidities and survival in 8 cancers | EN | publication | Impact of comorbid conditions (The Lancet) |
| Ovarian cancer ML prediction | EN | publication | ML model for ovarian cancer outcomes (ESMO) |

### 7.3 Richtlijnendatabase (Stretch Goal)

1. **Pre-scrape** priority oncology guidelines during application setup (prostaatcarcinoom, mammacarcinoom, colorectaal carcinoom, longcarcinoom, melanoom, blaascarcinoom).
2. **Clean:** Strip navigation, footers, and sidebars from scraped HTML.
3. **Chunk and embed:** Same 500-token / 50-overlap strategy.
4. **Store:** Write to ChromaDB collection `guidelines` with metadata: `cancer_type`, `guideline_section`, `url`.

If a user asks about a guideline that was not pre-indexed, the connector returns a `SourceResult` with empty data and a citation pointing to the expected URL on richtlijnendatabase.nl.

---

## 8. Claude Tool Definitions

The following tools are registered with Claude via the Anthropic tool-use API. Claude reads each tool's description and decides which to invoke based on the user's query and profile context.

### 8.1 search_kanker_nl

```
search_kanker_nl(
    query: str,              # free-text search query
    kankersoort: str | None, # optional cancer type filter (e.g. "borstkanker")
    section: str | None,     # optional section filter (e.g. "behandelingen")
) -> SourceResult
```

**Claude description:** "Search the kanker.nl patient information database for general information about cancer types, diagnosis, treatment options, side effects, and life after diagnosis. Content is in Dutch. Optionally filter by cancer type (kankersoort) and section."

### 8.2 get_cancer_incidence

```
get_cancer_incidence(
    cancer_type: str,        # cancer type name or NKR code
    period: str,             # year or range (e.g. "2020" or "2015-2020")
    sex: str | None,         # male / female / both
    age_group: str | None,   # e.g. "60-74"
    region: str | None,      # Dutch province name or "national"
) -> SourceResult
```

**Claude description:** "Query the Netherlands Cancer Registry for incidence (new cases) data. Returns counts and rates per 100,000 for the requested cancer type, period, and optional demographic filters. Data is authoritative and covers 1961 to present."

### 8.3 get_survival_rates

```
get_survival_rates(
    cancer_type: str,
    period: str,
    sex: str | None,
    age_group: str | None,
) -> SourceResult
```

**Claude description:** "Query the Netherlands Cancer Registry for survival statistics. Returns 1-year, 5-year, and 10-year relative survival rates for the specified cancer type and period, with optional sex and age group filters."

### 8.4 get_stage_distribution

```
get_stage_distribution(
    cancer_type: str,
    period: str,
    sex: str | None,
) -> SourceResult
```

**Claude description:** "Query the Netherlands Cancer Registry for stage distribution data. Returns the percentage breakdown by TNM stage (I, II, III, IV, Unknown) for the specified cancer type and period."

### 8.5 get_regional_cancer_data

```
get_regional_cancer_data(
    cancer_type: str,        # cancer group name (Dutch)
    sex: str | None,         # male / female / both
    postcode: str | None,    # 3- or 4-digit postcode prefix
) -> SourceResult
```

**Claude description:** "Look up regional cancer incidence data from the IKNL Cancer Atlas. Returns Standardized Incidence Ratios (SIRs) at postcode level for 25 cancer groups, showing whether a region has higher or lower incidence than the national average. Can render as a map."

When a postcode is provided, returns the SIR and credibility interval for that specific area. When omitted, returns a national summary with top-5 highest and lowest areas. Both modes set `visualizable = True`.

### 8.6 search_publications

```
search_publications(
    query: str,              # free-text search query
    source_type: str | None, # "report" or "publication"
    language: str | None,    # "nl" or "en"
) -> SourceResult
```

**Claude description:** "Search indexed scientific publications and institutional reports about cancer. Includes Lancet and ESMO papers (English) and IKNL reports on gender differences, metastatic cancer, and colorectal trends (Dutch). Filter by source type or language."

### 8.7 search_guidelines (Stretch Goal)

```
search_guidelines(
    query: str,              # free-text search query
    cancer_type: str | None, # optional cancer type filter
) -> SourceResult
```

**Claude description:** "Search Dutch clinical oncology guidelines from richtlijnendatabase.nl. Contains evidence-based treatment protocols and diagnostic recommendations. NOTE: only a subset of guidelines has been pre-indexed; for missing guidelines a direct URL is returned."

---

## 9. Chat Orchestrator Behaviour

### 9.1 Session Initialization

At session start, the system asks the user to identify their profile in Dutch:

> Welkom! Om u de beste informatie te geven, wil ik graag weten wie u bent:
> - Patient of naaste
> - Zorgprofessional
> - Beleidsmaker
> - (Overslaan)

The selected profile is stored in the session and injected into the system prompt. If the user skips, Claude infers the profile from conversation tone and vocabulary.

### 9.2 System Prompt Adaptation

The system prompt is dynamically composed based on the user profile:

| Profile | Tone | Source Priority | Depth |
|---------|------|----------------|-------|
| Patient / naaste | Warm, plain Dutch, empathetic | kanker.nl first, then statistics simplified | Summaries in accessible language, no jargon |
| Zorgprofessional | Clinical, precise | NKR-Cijfers + publications + richtlijnendatabase | Full data tables, percentages, staging details |
| Beleidsmaker | Analytical, comparative | Cancer Atlas + NKR trends + reports | Regional comparisons, trend analyses, aggregates |

The profile acts as a soft bias -- Claude can still use any source if the query demands it, but prioritizes according to the table.

### 9.3 Connector Selection Flow

When Claude receives a user question:

1. **Analyse intent:** informational, statistical, geographic, or clinical.
2. **Select connectors:** may call multiple tools (e.g. `search_kanker_nl` + `get_cancer_incidence` for "how common is lung cancer and what are the symptoms?").
3. **Merge results:** read each `SourceResult.summary`, reconcile contradictions, compose a single answer.
4. **Cite sources:** include URLs from `SourceResult.sources` in the response.
5. **Signal visualization:** if any result has `visualizable = True`, include chart data in the SSE stream.

### 9.4 Guardrails

| Guardrail | Implementation |
|-----------|---------------|
| Source citation on every response | System prompt requires per-claim attribution. Citations rendered as source cards. |
| Trusted sources only | No web search tool available. Only the registered connectors can be called. |
| No fabrication | Claude instructed to use only tool-returned content for factual claims. System prompt: "Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd." |
| Graceful decline | When no sources return results, Claude explicitly says so and redirects to kanker.nl or the user's huisarts. |
| No personal medical advice | System prompt: "Je bent een informatieassistent, geen arts. Geef nooit persoonlijk medisch advies." Redirects to huisarts or specialist for personal questions. |

---

## 10. Frontend Component Design

### 10.1 ChatMessage

Renders a single message bubble. For assistant messages, parses Markdown with inline source citations as clickable links. Detects `<!-- chart:json -->` blocks and replaces them with inline `<DataChart />` components.

### 10.2 SourceCard

Below each assistant response, a collapsible section displays consulted sources. Each card shows:
- **Source name** (kanker.nl, NKR-Cijfers, Kankeratlas, Publicaties, Richtlijnen)
- **Specific URL** (deep link to the exact content)
- **Reliability badge** with colour coding: Patienteninfo (blue), Cijfers (green), Atlas (orange), Publicatie (purple), Richtlijn (teal)
- **Contribution indicator** -- sources that contributed content are solid; sources queried but returning no results show a dashed border and "Geen resultaat"

Collapsible by default. Summary line: "3 bronnen geraadpleegd" with chevron toggle.

### 10.3 DataChart

Recharts wrapper accepting a `chartData` prop with a `type` field (`line`, `bar`, `value`):
- **Incidence trends** -- line chart with year on x-axis, count on y-axis
- **Incidence by age group** -- horizontal bar chart
- **Survival rates** -- line chart with confidence intervals as shaded area
- **SIR data** -- highlighted value with colour indicator (green/yellow/red scale) and optional comparison bar chart

### 10.4 FeedbackWidget

Thumbs up/down buttons below each response. Clicking sends `POST /api/feedback`. An "Informatie mist?" text link expands a single-line input for describing expected-but-missing information. Minimal, non-intrusive styling using muted colours and small sizing.

### 10.5 ProfileSelector

Sidebar component with three profile options:

| Profile | Label | Icon | Effect |
|---------|-------|------|--------|
| Patient / naaste | Patient / naaste | Heart | Plain language, kanker.nl prioritized |
| Zorgprofessional | Zorgprofessional | Stethoscope | Clinical terminology, richtlijnen prioritized |
| Beleidsmaker | Beleidsmaker | Chart-bar | Policy framing, Atlas + NKR prioritized |

Changeable at any time. Does not clear chat history. Subtle notification on switch.

---

## 11. Deployment

### 11.1 Docker Compose

Two services with a shared data volume:

```yaml
version: "3"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LLM_PROVIDER=anthropic
      - EMBEDDING_MODEL=multilingual-e5-large
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
```

### 11.2 Startup Sequence

1. Backend starts, loads config from environment variables.
2. Backend runs ingestion check: if ChromaDB collections are empty or missing, runs the ingestion pipeline (kanker.nl JSON + PDFs).
3. Backend caches NKR-Cijfers navigation items and filter-group definitions.
4. Backend health endpoint returns `healthy`.
5. Frontend starts, proxies API requests to backend.

### 11.3 Local Development

- **Backend:** `cd backend && uv run uvicorn main:app --reload --port 8000`
- **Frontend:** `cd frontend && pnpm dev`
- **Full stack:** `docker compose up --build`

---

## 12. Testing Strategy

### 12.1 Connector Unit Tests

Mock external API responses and verify each connector:
- Returns a valid `SourceResult` with populated `summary` and `sources`
- Handles API errors gracefully (returns descriptive error summary, does not throw)
- Applies metadata filters correctly (kanker.nl, publications)
- Builds correct request bodies for NKR-Cijfers (separate formats for `/data` vs `/filter-groups`)
- Maps cancer group names to IDs correctly (Cancer Atlas)

### 12.2 Integration Tests

Real API calls against live endpoints (NKR-Cijfers, Cancer Atlas):
- Verify navigation items can be fetched and cached
- Verify incidence data returns non-empty results for known cancer types
- Verify Cancer Atlas SIR data returns valid percentiles for known postcodes
- Run with `pytest -m integration` flag, excluded from CI by default

### 12.3 Frontend Component Tests

React Testing Library tests for each component:
- `ChatMessage` renders Markdown correctly and extracts chart blocks
- `SourceCard` displays correct badge colours and handles collapsed/expanded states
- `DataChart` renders the correct Recharts component type based on `chartData.type`
- `FeedbackWidget` sends correct payload on thumbs up/down
- `ProfileSelector` emits profile change events and shows notification

### 12.4 E2E Smoke Test

End-to-end test verifying the full pipeline:
1. Send a chat message via the `/api/chat/stream` endpoint.
2. Verify SSE stream contains `token` events with non-empty text.
3. Verify at least one `source_card` event is emitted.
4. Verify the `done` event includes `sources_tried` with at least one connector name.
5. For a statistical question, verify a `chart_data` event is emitted.

---

## 13. Security and Privacy Considerations

- **No user data stored beyond session.** Chat history is maintained in-memory per session and discarded when the session ends. No PII is persisted.
- **Feedback is anonymous.** The feedback database stores session IDs but no user identifiers.
- **API keys are environment variables.** Never committed to the repository. Docker Compose reads from `.env` file excluded via `.gitignore`.
- **No personal medical advice.** The system prompt explicitly prevents Claude from providing diagnosis, prognosis, or treatment recommendations for individual cases.

---

## 14. Success Criteria Mapping

This section maps each hackathon judging criterion to the technical design decisions that address it.

| Domain | # | Criterion | Design Response |
|--------|---|-----------|-----------------|
| Information Integrity | 1 | Provides an answer | Claude tool-use queries multiple sources per question. If one connector returns no results, others are tried before falling back to an explicit "no information found" response. |
| Information Integrity | 2 | Source provenance | Source cards with URLs and reliability badges on every response. Inline Markdown citations link directly to source pages. |
| Information Integrity | 3 | Trusted sources only | Five connectors limited to IKNL-approved sources. No web search tool available. Claude cannot access anything outside the registered tools. |
| Information Integrity | 4 | No fabrication | RAG-grounded responses. System prompt: "Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd." Source cards provide auditability. |
| Information Integrity | 5 | Decline when uncertain | System prompt instructs graceful decline with redirect to kanker.nl or huisarts. Source cards showing "Geen resultaat" make transparency visible. |
| Usability | 1 | Pathways for target groups | Three profiles with adapted system prompts, source prioritization, and response formatting. |
| Usability | 2 | Modern information seeking | Conversational chat with streaming, natural language in Dutch, inline data visualization. |
| Usability | 3 | Faster access | Single chat replaces 4+ separate IKNL websites. One question triggers cross-source lookups and synthesized answers. |
| Ethics | 1 | Ethical safeguards | System prompt declines personal medical advice and redirects to healthcare professionals. |
| Advanced | 1 | Connects sources | All 5+ IKNL data sources unified through Claude tool-use orchestration. |
| Advanced | 2 | Creative understanding | Inline charts, reliability badges, profile-adapted explanations translate raw data into comprehensible formats. |
| Advanced | 3 | Future potential | Connector interface makes adding sources straightforward. LiteLLM enables provider-agnostic upgrades. |
| Bonus | - | Feedback mechanism | Thumbs up/down + "Informatie mist?" per response, stored in SQLite with CSV export for IKNL review. |

---

## 15. Open Questions

1. **Embedding model final choice.** Benchmark `text-embedding-3-small` vs `multilingual-e5-large` on a set of 50 Dutch cancer queries before the demo to determine recall quality.
2. **NKR-Cijfers rate limiting.** Unclear if there are request-per-minute limits. The connector should implement exponential backoff as a precaution.
3. **Richtlijnendatabase scraping legality.** Confirm with IKNL legal/comms whether pre-scraping for a hackathon demo is acceptable before implementing the stretch connector.
4. **Cross-collection search.** Should Claude be able to search all three ChromaDB collections in a single tool call, or always select one? Current design uses one tool per collection.
5. **Cancer Atlas API availability.** Verify the Strapi API is publicly accessible without authentication, or whether data needs to be pre-cached.
