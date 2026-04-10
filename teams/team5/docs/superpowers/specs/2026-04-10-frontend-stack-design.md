# Frontend & Tech Stack — Design Spec

> Cancer Information Chat System — Hackathon BOM x IKNL
> Date: 2026-04-10

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts |
| Chat streaming | Server-Sent Events (SSE) via fetch |
| Backend | FastAPI, Python 3.11+, async |
| LLM | Anthropic Claude (primary) via anthropic SDK, LiteLLM for provider abstraction, Ollama fallback |
| Orchestration | Claude native tool-use (no framework) |
| Vector store | ChromaDB (persistent, file-based) |
| Embeddings | text-embedding-3-small (OpenAI) or multilingual-e5-large (local via sentence-transformers) |
| PDF extraction | PyMuPDF (fitz) |
| Feedback storage | SQLite |
| Dev tooling | uv (Python), pnpm (Node), Docker Compose for one-command startup |

### Rationale

- **Next.js 14 App Router** provides server components, streaming support, and a modern React foundation without over-engineering. App Router aligns with the SSE streaming model and keeps the frontend thin.
- **Tailwind CSS** enables rapid prototyping during the hackathon while producing a clean, responsive UI without writing custom CSS files.
- **Recharts** is chosen over heavier charting libraries (D3, Highcharts) because it integrates natively with React components and covers the bar/line chart use cases needed for NKR-Cijfers data without additional complexity.
- **FastAPI with async** gives us native SSE support, automatic OpenAPI docs for demo purposes, and excellent performance for streaming LLM responses.
- **Claude native tool-use** avoids the overhead of LangChain or similar frameworks. The orchestrator calls Claude with tool definitions; Claude decides which connectors to invoke. This keeps the architecture simple and debuggable.
- **LiteLLM** provides a fallback path: if the Anthropic API is unavailable or rate-limited during the demo, we can switch to Ollama or another provider without code changes.
- **ChromaDB** (file-based) requires zero infrastructure — no database server, no Docker dependency for the vector store. The persistent directory lives in `data/chromadb/` and survives restarts.
- **SQLite** for feedback storage follows the same zero-infrastructure principle. A single `.db` file, no server process.
- **uv + pnpm** are modern, fast package managers that reduce install times during hackathon setup. Docker Compose wraps everything for judges who want a one-command experience.

---

## Frontend Components

### Chat Interface

The chat interface is the primary interaction surface. It occupies the center of the viewport with a sidebar on the left for profile selection and session controls.

**Streaming responses via SSE from FastAPI.** The frontend opens an SSE connection to `/api/chat/stream` for each user message. Tokens arrive incrementally and are rendered in real time, giving the user immediate visual feedback that the system is working. The SSE client (`lib/chat-client.ts`) handles reconnection, error states, and stream completion.

**Messages render Markdown with inline source citations as clickable links.** Claude's responses include citation markers like `[kanker.nl: Borstkanker](https://www.kanker.nl/...)` which the Markdown renderer turns into clickable links. This keeps provenance visible inline without requiring the user to scroll to a separate section.

**User profile selector in sidebar (patient / professional / policymaker) — changeable anytime.** The selected profile is sent with each chat request and affects:
- The system prompt (tone, vocabulary, level of detail)
- Source prioritization (patients see kanker.nl content first; professionals see richtlijnen and NKR data first)
- Whether statistical data is presented as plain-language summaries or as charts with raw numbers

**Dutch as default language, English fallback.** The UI chrome (buttons, labels, placeholders) is in Dutch. Claude is instructed to respond in the same language as the user's query, defaulting to Dutch. All UI strings are extracted into a simple i18n object for maintainability.

**Responsive design, works on mobile.** Tailwind's responsive utilities ensure the chat interface stacks vertically on small screens. The sidebar collapses into a hamburger menu on mobile. Chat messages use full viewport width on phones.

### Source Cards

Below each assistant response, a collapsible section displays the sources that were consulted during answer generation.

**Each card contains:**
- **Source name** — e.g., kanker.nl, NKR-Cijfers, Kankeratlas, IKNL Publicaties, Richtlijnendatabase
- **Specific URL** — deep link to the exact page, dataset, or document section
- **Reliability badge** — visual indicator of the source type:
  - `Patiënteninfo` (blue) for kanker.nl content
  - `Cijfers` (green) for NKR statistical data
  - `Atlas` (orange) for Cancer Atlas regional data
  - `Publicatie` (purple) for PDF reports and publications
  - `Richtlijn` (teal) for clinical guidelines

**Visual indicator of source contribution.** Sources that contributed content to the answer are shown with a solid badge and full opacity. Sources that were queried but returned no relevant results are shown with a dashed border and reduced opacity, labeled "Geen resultaat." This transparency helps users (and IKNL judges) see exactly what the system tried.

**Collapsible by default** to keep the chat clean. A summary line like "3 bronnen geraadpleegd" with a chevron toggle expands the full card list.

### Data Visualization (Inline)

When the orchestrator retrieves statistical data from NKR-Cijfers or the Cancer Atlas, the frontend renders it as an inline chart within the chat message — not in a separate panel or modal.

**NKR-Cijfers statistical data** is rendered as bar or line charts. Examples:
- Incidence trends over years → line chart with year on x-axis, count on y-axis
- Incidence by age group → horizontal bar chart
- Survival rates → line chart with confidence intervals shown as a shaded area

**Cancer Atlas SIR data** is rendered as a highlighted value with context: "SIR: 1.12 (hoger dan gemiddeld)" with a small color indicator (green/yellow/red scale). For regional comparisons, a simple bar chart comparing the queried region to the national average.

**Recharts integration.** The `DataChart.tsx` component accepts a `chartData` prop with a `type` field (`line`, `bar`, `value`) and renders the appropriate Recharts component. Chart data is structured by the backend orchestrator and included in the SSE stream as a JSON block between markdown content sections.

**Chart rendering within chat messages.** The `ChatMessage.tsx` component parses the assistant's response and identifies `<!-- chart:json -->` blocks. These are replaced with `<DataChart />` components inline. This approach keeps charts contextual — they appear exactly where they're relevant in the explanation.

### Profile Selector

A sidebar component offering three user profiles:

| Profile | Label (Dutch) | Icon | Effect |
|---|---|---|---|
| Patient / naaste | Patient / naaste | Heart icon | Plain language, kanker.nl prioritized, stats simplified |
| Zorgprofessional | Zorgprofessional | Stethoscope icon | Clinical terminology allowed, richtlijnen prioritized, raw data shown |
| Beleidsmaker | Beleidsmaker | Chart-bar icon | Policy framing, NKR-Cijfers and Atlas prioritized, trends emphasized |

**Changeable at any time during conversation.** Switching profiles mid-conversation does not clear chat history. The new profile is applied starting from the next user message. A subtle notification ("Profiel gewijzigd naar Zorgprofessional") appears in the chat to acknowledge the switch.

**Affects system prompt and source prioritization.** The profile value is included in the request payload. The backend orchestrator uses it to:
1. Select the appropriate system prompt variant
2. Reorder tool priority (which connectors Claude tries first)
3. Adjust response formatting instructions

### Feedback Widget

Each assistant response includes a minimal feedback mechanism:

**Thumbs up / thumbs down** — two small icon buttons below each response. Clicking one highlights it and sends a `POST /api/feedback` with:
- `session_id`
- `message_id`
- `rating` (positive / negative)
- `timestamp`

**"Informatie mist?" button** — a text link below the thumbs. Clicking it expands a small text input where the user can describe what information they expected but didn't find. Submitting logs:
- The original query
- The sources that were tried (from source cards metadata)
- The user's comment
- The selected profile at time of query

**Stored in SQLite for IKNL to review.** The `feedback.db` file lives in `data/feedback.db`. A simple admin endpoint (`GET /api/feedback/export`) returns all feedback as CSV for post-hackathon analysis.

**Minimal, non-intrusive UX.** The feedback buttons use muted colors and small sizing. They don't compete with the response content for attention. The "Informatie mist?" flow is a single text field with a submit button — no multi-step forms.

---

## Project Structure

```
├── backend/
│   ├── main.py                 # FastAPI app + SSE endpoint
│   ├── orchestrator.py         # Chat orchestrator, Claude tool-use
│   ├── connectors/
│   │   ├── base.py             # SourceConnector interface + SourceResult
│   │   ├── kanker_nl.py        # Vector search over kanker.nl
│   │   ├── nkr_cijfers.py      # NKR-Cijfers API wrapper
│   │   ├── cancer_atlas.py     # Cancer Atlas API wrapper
│   │   ├── publications.py     # PDF/report vector search
│   │   └── richtlijnen.py      # Richtlijnendatabase (stretch)
│   ├── ingestion/
│   │   ├── sitemap_builder.py  # kanker.nl JSON → sitemap tree
│   │   ├── vectorize.py        # Chunking + embedding pipeline
│   │   └── pdf_extractor.py    # PDF text extraction
│   ├── models.py               # Pydantic models (session, citation, feedback)
│   └── config.py               # Settings, API keys, provider config
├── frontend/
│   ├── app/
│   │   ├── page.tsx            # Chat page
│   │   └── api/                # (optional BFF routes)
│   ├── components/
│   │   ├── ChatMessage.tsx
│   │   ├── SourceCard.tsx
│   │   ├── DataChart.tsx
│   │   ├── FeedbackWidget.tsx
│   │   └── ProfileSelector.tsx
│   └── lib/
│       └── chat-client.ts      # SSE streaming client
├── data/                       # Existing hackathon data (kanker.nl JSON, PDFs)
├── docs/
│   └── success-criteria.md
└── docker-compose.yml
```

### Key Architectural Decisions

**Backend and frontend are separate processes** connected via HTTP/SSE. This allows independent development and deployment. During the hackathon, both run locally via Docker Compose. The frontend proxies API requests to the backend via Next.js rewrites in `next.config.js`.

**Connectors are the abstraction boundary.** Each data source gets its own connector module implementing the `SourceConnector` interface from `base.py`. This means:
- Adding a new source = adding one file in `connectors/`
- Each connector is independently testable
- The orchestrator doesn't know implementation details of any source

**Ingestion is a separate pipeline.** The `ingestion/` directory contains scripts that run once (or periodically) to build the vector store. They are not part of the request path. This separation keeps the chat response time fast — all retrieval happens against pre-built indexes.

**No BFF requirement.** The frontend can call the FastAPI backend directly. The `api/` directory in the frontend is reserved for optional server-side routes (e.g., if we need to proxy requests for CORS reasons during development), but the primary API surface is FastAPI.

---

## Success Criteria Mapping

This section maps each hackathon success criterion to the specific design decisions that address it.

### Domain 1: Information Integrity (Informatiebetrouwbaarheid)

| # | Criterion | How the Design Addresses It |
|---|---|---|
| 1 | **Provides an answer** | Claude tool-use queries relevant sources for every user question. The orchestrator always attempts an answer by trying multiple connectors in priority order. If one source has no results, others are tried before falling back to a "no information found" response. |
| 2 | **Source provenance** | Every response includes source cards with specific URLs and reliability badges. Inline citations in the Markdown link directly to the source page. The user always knows where information came from. |
| 3 | **Trusted sources only** | Connectors are limited to IKNL-approved sources (kanker.nl, NKR-Cijfers, Cancer Atlas, IKNL publications, Richtlijnendatabase). No web search tool is available to Claude. The tool definitions only include these five connectors — Claude cannot access anything else. |
| 4 | **No fabrication** | Responses are RAG-grounded: Claude receives retrieved content in tool results and is instructed via system prompt to only use that content for factual claims. Source cards provide auditability. The system prompt explicitly states: "Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd." |
| 5 | **Decline when uncertain** | The system prompt instructs Claude to decline with a redirect when no sources return relevant matches: "Als je geen relevante informatie vindt, zeg dat eerlijk en verwijs door naar kanker.nl of de huisarts." The source cards showing "Geen resultaat" make this transparent. |

### Domain 2: Usability (Gebruiksvriendelijkheid)

| # | Criterion | How the Design Addresses It |
|---|---|---|
| 1 | **Pathways for target groups** | Three distinct profiles (Patient/naaste, Zorgprofessional, Beleidsmaker) each get adapted system prompts, source prioritization, and response formatting. A patient asking about survival rates gets a plain-language explanation; a professional gets the statistical data with confidence intervals. |
| 2 | **Modern information seeking** | Conversational chat interface with streaming responses, natural language queries in Dutch, and inline data visualization. No need to learn query syntax or navigate complex websites. |
| 3 | **Faster access to information** | A single chat interface replaces visiting 4+ separate IKNL websites. One question can trigger lookups across kanker.nl, NKR-Cijfers, Cancer Atlas, and publications simultaneously. The user gets a synthesized answer instead of having to piece together information from multiple tabs. |

### Domain 3: Ethics (Ethisch verantwoord)

| # | Criterion | How the Design Addresses It |
|---|---|---|
| 1 | **Ethical safeguards** | The system prompt includes an ethical filter that declines personal medical advice. When a user asks "Moet ik chemo nemen?" the system responds with general information and redirects to their huisarts or specialist. The filter covers: personal treatment decisions, diagnosis, prognosis for individual cases, and medication recommendations. |

### Domain 4: Advanced (Geavanceerd)

| # | Criterion | How the Design Addresses It |
|---|---|---|
| 1 | **Connects multiple sources** | All 5+ IKNL data sources are unified through Claude's tool-use orchestration. A single question like "Hoe vaak komt borstkanker voor en wat zijn de behandelopties?" triggers both NKR-Cijfers (incidence data) and kanker.nl (treatment information) connectors, with the answer synthesizing both. |
| 2 | **Creative understanding of information** | Inline data visualization (Recharts) turns raw NKR numbers into comprehensible charts. Source cards with reliability badges give visual structure to provenance. Profile-adapted explanations translate the same data into different registers depending on the audience. |
| 3 | **Future potential** | The connector interface (`SourceConnector` in `base.py`) makes adding new sources straightforward — implement the interface, register the tool. LiteLLM provides provider-agnostic LLM access, so upgrading to a better model requires only a config change. The architecture is designed for extensibility beyond the hackathon. |

### Bonus: Feedback Mechanism

| Criterion | How the Design Addresses It |
|---|---|
| **User feedback** | Thumbs up/down per response provides quick signal. "Informatie mist?" captures detailed feedback about gaps — the exact query, which sources were tried, and what the user expected. All stored in SQLite (`data/feedback.db`) with a CSV export endpoint for IKNL to review post-hackathon. |

---

## Open Questions & Stretch Goals

### Open Questions

1. **Embedding model choice.** Do we use OpenAI's `text-embedding-3-small` (better quality, requires API key, costs money) or `multilingual-e5-large` (free, local, good Dutch support, slower)? Decision depends on hackathon API budget.
2. **Cancer Atlas API availability.** Need to verify the Cancer Atlas API is publicly accessible or if we need to scrape/cache the data.
3. **Richtlijnendatabase access.** Marked as stretch goal. Need to check if there's an API or if we need to work from cached/scraped content.

### Stretch Goals

- **Conversation memory** — maintain context across multiple turns so follow-up questions like "En voor mannen?" work without repeating the full context.
- **Export conversation** — allow users to download the chat as a PDF with all sources and charts included.
- **Source comparison view** — when multiple sources provide overlapping information, show a side-by-side comparison highlighting agreements and differences.
- **Richtlijnendatabase connector** — if API access is available, add clinical guideline search as a sixth source.
