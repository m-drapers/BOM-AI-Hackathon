# Architecture Document -- IKNL Cancer Information Chat System

> **Project:** BrabantHack_26 IKNL Hackathon
> **Status:** Living document -- updated as the system evolves

---

## 1. System Overview

This system provides a conversational interface that unifies IKNL's distributed
cancer information sources into a single, accessible experience. Rather than
requiring users to navigate five separate platforms (kanker.nl, NKR-Cijfers,
Cancer Atlas, scientific publications, richtlijnendatabase), the chat interface
retrieves, synthesises, and presents information from all of them in one turn.

Core capabilities:

- **RAG retrieval** -- vector search over kanker.nl content, publications, and
  clinical guidelines, combined with structured API queries against NKR-Cijfers
  and the Cancer Atlas.
- **Inline data visualisation** -- when the answer involves statistics or
  trends, the system returns chart-ready data that the frontend renders as
  interactive Recharts visualisations directly in the chat thread.
- **User profile adaptation** -- the same interface serves patients/public,
  healthcare professionals, and researchers. A profile selector adjusts tone,
  terminology, source priority, and depth of detail via system prompt injection.

All information originates exclusively from IKNL-trusted sources. The model
cannot perform web searches or consult external data.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Next.js Frontend                       │
│  Chat UI (streaming) | Source Cards | Data Viz (charts)  │
└────────────────────────┬────────────────────────────────┘
                         │ SSE / streaming
┌────────────────────────┴────────────────────────────────┐
│                   FastAPI Backend                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │            Chat Orchestrator                     │    │
│  │  - User profiling (stakeholder type + intent)    │    │
│  │  - Claude native tool-use (primary)              │    │
│  │  - LiteLLM provider abstraction (Ollama fallback)│    │
│  └──────┬──────────┬──────────┬──────────┬─────────┘    │
│         │          │          │          │               │
│  ┌──────┴───┐ ┌────┴────┐ ┌──┴───┐ ┌───┴──────────┐   │
│  │kanker.nl │ │NKR-Cijf.│ │Atlas │ │Publications  │   │
│  │Vector    │ │API      │ │API   │ │PDF/Text      │   │
│  │Search    │ │Connector│ │Conn. │ │Search        │   │
│  └──────┬───┘ └─────────┘ └──────┘ └──────────────┘   │
│         │                                               │
│  ┌──────┴──────────────┐                                │
│  │  ChromaDB (vector)  │                                │
│  └─────────────────────┘                                │
└─────────────────────────────────────────────────────────┘
```

The frontend communicates with the backend over a single SSE streaming
endpoint. The backend orchestrator fans out to one or more connectors per turn,
then synthesises the results into a streamed response.

---

## 3. Layers

### 3.1 Presentation Layer

| Aspect      | Choice                                    |
| ----------- | ----------------------------------------- |
| Framework   | Next.js 14 (App Router)                   |
| Language    | TypeScript                                |
| Styling     | Tailwind CSS                              |
| Charts      | Recharts                                  |

The frontend is a single-page chat interface with the following components:

- **Chat thread** -- messages stream in token-by-token via SSE. The UI
  progressively renders Markdown as tokens arrive.
- **Source cards** -- every assistant message includes provenance cards that
  link back to the original IKNL source (kanker.nl page, NKR dataset, Atlas
  map, publication DOI, guideline section). Cards are rendered below the
  message text.
- **Inline charts** -- when the orchestrator returns structured data (e.g.
  incidence rates over time), the frontend renders a Recharts bar/line/area
  chart directly inside the chat thread. No separate dashboard required.
- **Profile selector** -- a header control lets the user choose their role:
  patient/public, healthcare professional, or researcher. This is sent with
  every request and affects the system prompt.
- **Feedback widget** -- thumbs up/down plus optional free-text on every
  assistant message. Stored server-side for post-hackathon analysis.

### 3.2 API Layer

| Aspect      | Choice                                    |
| ----------- | ----------------------------------------- |
| Framework   | FastAPI (async)                           |
| Transport   | SSE for chat, REST for feedback/config    |
| Auth        | None (hackathon scope)                    |

Endpoints:

| Method | Path               | Purpose                                 |
| ------ | ------------------ | --------------------------------------- |
| POST   | `/api/chat`        | SSE streaming chat completions          |
| POST   | `/api/feedback`    | Store thumbs up/down + comment          |
| GET    | `/api/health`      | Readiness probe                         |
| GET    | `/api/sources`     | List available source connectors        |

The `/api/chat` endpoint accepts a JSON body with the conversation history,
selected user profile, and optional filters. It returns an SSE event stream
where each event is either a text delta, a source card payload, or a chart
data payload. The frontend distinguishes event types via a `type` field in the
SSE data.

### 3.3 Orchestration Layer

The orchestrator is the core decision-making component. It sits between the API
layer and the connectors.

**LLM integration:**

- **Primary:** Claude via the Anthropic API with native tool-use. Claude
  receives tool definitions for each connector and autonomously decides which
  tools to call based on the user's question. This eliminates the need for a
  separate routing/planning layer.
- **Fallback:** Ollama (local open-source model) via LiteLLM's provider
  abstraction. If the Anthropic API is unreachable during the demo, the system
  degrades gracefully to a local model with the same tool definitions.
- **Provider abstraction:** LiteLLM wraps both providers behind a unified
  interface, so the orchestrator code does not branch on provider type.

**Profile injection:**

Before every LLM call the orchestrator prepends a profile-specific system
prompt segment. This segment adjusts:

- **Tone** -- empathetic and jargon-free for patients; precise and clinical for
  professionals; data-dense and citation-heavy for researchers.
- **Source priority** -- patients see kanker.nl content first; professionals see
  guidelines first; researchers see publications and NKR data first.
- **Depth** -- patients get summaries; researchers get full statistical context.

**No LangGraph:**

We deliberately chose Claude's native tool-use over a LangGraph/agent-graph
approach. For this use case the routing logic is simple enough that a single
tool-use turn (occasionally two) covers every query pattern. LangGraph would
add latency, complexity, and a dependency with no corresponding benefit.

### 3.4 Connector Layer

All connectors implement a common `SourceConnector` interface:

```python
class SourceConnector(Protocol):
    name: str
    description: str

    async def search(self, query: str, filters: dict | None = None) -> list[SourceResult]:
        ...

    def to_tool_definition(self) -> dict:
        """Return the Claude tool-use JSON schema for this connector."""
        ...
```

Each connector is registered as a tool with Claude. The LLM sees the tool name,
description, and parameter schema, and calls the appropriate tool(s) per turn.

#### 3.4.1 kanker.nl -- Vector Search

- **Source:** Patient-facing cancer information pages from kanker.nl.
- **Ingestion:** Pages are scraped, chunked (~500 tokens), embedded with a
  sentence-transformer model, and stored in ChromaDB.
- **Retrieval:** Cosine similarity search with optional metadata filters
  (cancer type, topic category). Top-k results returned with page URL for
  source attribution.

#### 3.4.2 NKR-Cijfers -- REST API Connector

- **Source:** The Netherlands Cancer Registry statistics API (NKR-Cijfers).
- **Integration:** Direct REST calls to the NKR-Cijfers API. The connector
  translates the user's natural-language question into structured API
  parameters (cancer type, year range, measure).
- **Output:** Returns tabular data suitable for chart rendering, plus a
  human-readable summary.

#### 3.4.3 Cancer Atlas -- REST API Connector

- **Source:** Regional cancer incidence/mortality maps.
- **Integration:** REST calls to the Cancer Atlas API. Returns geospatial
  data and regional comparisons.
- **Output:** Regional statistics, optionally formatted for map or chart
  visualisation.

#### 3.4.4 Publications -- Vector Search

- **Source:** Scientific publications and research reports from IKNL.
- **Ingestion:** PDFs and text documents are parsed, chunked, embedded, and
  stored in ChromaDB (separate collection from kanker.nl).
- **Retrieval:** Semantic search with metadata filters (year, cancer type,
  author). Results include DOI or URL for citation.

#### 3.4.5 Richtlijnendatabase -- Vector Search (stretch goal)

- **Source:** Dutch clinical oncology guidelines.
- **Ingestion:** Guideline sections are chunked, embedded, and stored in a
  third ChromaDB collection.
- **Retrieval:** Semantic search with section/chapter metadata. Primarily
  surfaced for healthcare professional and researcher profiles.

### 3.5 Storage Layer

| Store    | Technology     | Purpose                                     |
| -------- | -------------- | ------------------------------------------- |
| Vectors  | ChromaDB       | Embedding storage and similarity search     |
| Feedback | SQLite         | User feedback (thumbs, comments, timestamps)|

**ChromaDB** runs in file-based (persistent) mode. No server process required.
Three collections:

1. `kanker_nl` -- patient information page embeddings
2. `publications` -- scientific publication embeddings
3. `guidelines` -- richtlijnendatabase embeddings (stretch)

**SQLite** stores feedback rows. A single file, zero configuration, queryable
with standard SQL for post-hackathon analysis.

Both stores are file-based by design: zero infrastructure, instant setup,
portable across developer machines, and trivially backed up by copying a
directory.

---

## 4. Data Flow

A complete request lifecycle:

```
1. User types a question in the chat UI and hits send.
   The frontend includes: message history, selected profile, any active filters.

2. Frontend POSTs to /api/chat. The connection stays open for SSE streaming.

3. API layer validates the request and hands it to the orchestrator.

4. Orchestrator builds the LLM prompt:
   a. System prompt (base instructions + profile-specific segment)
   b. Tool definitions (one per connector)
   c. Conversation history

5. Orchestrator calls Claude (or Ollama fallback) via LiteLLM.

6. Claude analyses the question and returns one or more tool_use blocks.
   Example: for "How common is breast cancer in Noord-Brabant?"
   Claude might call both nkr_cijfers_search(cancer_type="breast")
   and cancer_atlas_search(cancer_type="breast", region="Noord-Brabant").

7. Orchestrator executes the requested connector calls in parallel (asyncio).

8. Connector results are returned to Claude as tool_result messages.

9. Claude synthesises a final response that:
   - Answers the question in the appropriate tone for the user profile
   - References specific sources
   - Includes structured chart data if statistics are involved

10. The orchestrator streams Claude's response token-by-token over SSE.
    Special SSE event types:
    - "delta"   : text token
    - "source"  : source card JSON (url, title, connector name)
    - "chart"   : chart data JSON (type, labels, datasets)
    - "done"    : end of stream

11. Frontend renders tokens as they arrive. When a "source" event arrives,
    a source card is appended below the message. When a "chart" event
    arrives, a Recharts component is rendered inline.

12. User can click thumbs up/down, which POSTs to /api/feedback.
```

---

## 5. Key Design Decisions

### 5.1 Claude Native Tool-Use over LangGraph

LangGraph and similar agent frameworks add a routing/planning layer on top of
the LLM. For our use case -- a bounded set of five connectors with clear
descriptions -- Claude's built-in tool-use is sufficient. The LLM reads the
tool schemas, decides which to call, and we execute them. This gives us:

- **Lower latency** -- no extra planning step or graph traversal.
- **Less code** -- no graph definitions, node functions, or edge conditions.
- **Easier debugging** -- the tool-use request/response is a single JSON
  turn, fully visible in logs.

### 5.2 LiteLLM for Provider Abstraction

Hackathon demos are high-stakes, low-reliability environments. If the
Anthropic API goes down or rate-limits us mid-demo, LiteLLM lets us switch
to a local Ollama model with a single environment variable change. The
orchestrator code does not change at all.

### 5.3 ChromaDB File-Based (Zero Infrastructure)

A hackathon project cannot depend on managed infrastructure. ChromaDB in
persistent file mode gives us:

- Vector search with no server process.
- Data that survives restarts (unlike in-memory mode).
- A directory that can be committed to the repo or shared via a zip.

### 5.4 Filter-Aware Vector Retrieval

Naive RAG retrieves the top-k most similar chunks regardless of metadata.
Our connectors support metadata filters (cancer type, year, category) that
are applied *before* similarity search. This means:

- A query about "breast cancer" never returns lung cancer chunks.
- Year filters narrow the publication search space.
- Category filters isolate kanker.nl content by topic.

This dramatically improves retrieval precision without increasing k.

### 5.5 SSE Streaming

Server-Sent Events provide real-time token-by-token display. Compared to
WebSockets, SSE is:

- Simpler (unidirectional, no handshake upgrade).
- Natively supported by browsers (`EventSource` API).
- Sufficient -- the client only sends data via POST, never mid-stream.

### 5.6 Profile-Based Adaptation

Three target groups use the same interface:

| Profile                 | Tone               | Primary Sources               |
| ----------------------- | ------------------- | ----------------------------- |
| Patient / Public        | Empathetic, simple  | kanker.nl, Cancer Atlas       |
| Healthcare Professional | Clinical, precise   | Richtlijnendatabase, NKR      |
| Researcher              | Data-dense, cited   | Publications, NKR-Cijfers     |

Profile selection is a UI control, not authentication. The profile is injected
into the system prompt so that Claude adapts its language, source priority, and
level of detail automatically.

---

## 6. Security and Guardrails

### 6.1 Trusted Sources Only

Claude has no access to web search, browsing, or external APIs. The only tools
available are the five IKNL connectors. This means every fact in the response
can be traced to a known, vetted source.

### 6.2 Source Provenance on Every Response

Every assistant message includes one or more source cards. Each card contains:

- The connector that provided the information (e.g. "kanker.nl", "NKR-Cijfers").
- A direct URL or reference to the original content.
- The relevance score (for vector search results).

Users can always verify claims against the original source.

### 6.3 Decline When Uncertain

The system prompt instructs Claude to explicitly state when it cannot find
sufficient information rather than speculating. In such cases it redirects
the user to the appropriate IKNL platform or suggests contacting a healthcare
professional.

### 6.4 No Personal Medical Advice

An ethical filter is embedded in the system prompt. The model will:

- Never diagnose or recommend treatment.
- Always clarify that information is general, not personalised.
- Recommend consulting a healthcare provider for personal medical questions.

This is enforced at the prompt level and reinforced by the constraint that
only IKNL educational and statistical sources are available -- no clinical
decision-support tools are exposed.

---

## 7. Technology Stack Summary

| Component          | Technology                          |
| ------------------ | ----------------------------------- |
| Frontend           | Next.js 14, TypeScript, Tailwind CSS|
| Charts             | Recharts                            |
| Backend            | FastAPI (Python, async)             |
| LLM (primary)      | Claude via Anthropic API            |
| LLM (fallback)     | Ollama (local)                      |
| LLM abstraction    | LiteLLM                             |
| Vector store       | ChromaDB (file-based persistent)    |
| Embeddings         | Sentence-transformers               |
| Feedback store     | SQLite                              |
| Streaming          | Server-Sent Events (SSE)            |

---

## 8. Directory Structure (Target)

```
/
├── frontend/               # Next.js application
│   ├── app/                # App Router pages and layouts
│   ├── components/         # Chat, SourceCard, Chart, ProfileSelector
│   └── lib/                # SSE client, API helpers, types
├── backend/                # FastAPI application
│   ├── api/                # Route handlers (chat, feedback, health)
│   ├── orchestrator/       # Chat orchestrator, prompt builder
│   ├── connectors/         # SourceConnector implementations
│   │   ├── kanker_nl.py
│   │   ├── nkr_cijfers.py
│   │   ├── cancer_atlas.py
│   │   ├── publications.py
│   │   └── guidelines.py
│   ├── storage/            # ChromaDB and SQLite wrappers
│   └── models/             # Pydantic request/response schemas
├── data/                   # ChromaDB persistent directory, SQLite file
├── scripts/                # Ingestion scripts (scrape, chunk, embed)
└── docs/                   # Architecture, ADRs, runbooks
    └── 01-architecture/
        └── README.md       # (this file)
```

---

## 9. Open Questions and Stretch Goals

- **Richtlijnendatabase access** -- confirming API/scraping feasibility.
  Marked as a stretch connector.
- **Conversation memory** -- currently stateless (full history sent each
  turn). If turns grow long, a summarisation step may be needed.
- **Embedding model selection** -- evaluating multilingual sentence-transformers
  for Dutch-language content quality.
- **Chart type selection** -- Claude decides the chart type; we may need to
  constrain the schema to the types Recharts supports well.
- **Caching** -- frequently asked questions could hit a response cache to
  reduce LLM calls. Not in MVP scope.
