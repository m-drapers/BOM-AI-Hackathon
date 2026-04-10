# Cancer Information Chat -- Design Spec

## Overview

BrabantHack_26 IKNL Med Tech track hackathon project. A chat-based interface that connects IKNL's distributed trusted cancer information sources (kanker.nl, NKR-Cijfers, Cancer Atlas, publications, richtlijnendatabase) into a unified, accessible experience. Users get answers grounded in trusted sources with full citation provenance.

**Target groups:** patients and loved ones, healthcare professionals, policymakers. The system adapts tone and source priority based on user profile.

**Tech stack:** Python FastAPI backend + Next.js React frontend. Claude (Anthropic) as primary LLM with LiteLLM for provider abstraction and Ollama local fallback.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Next.js Frontend                       │
│  Chat UI (streaming) | Source Cards | Data Viz (charts)  │
└────────────────────────┬────────────────────────────────┘
                         │ SSE/streaming
┌────────────────────────┴────────────────────────────────┐
│                FastAPI Backend                            │
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

### Key architectural decisions

**Claude native tool-use instead of LangGraph.** Claude's built-in tool-use capability handles both simple single-source lookups and complex multi-source queries without needing an external orchestration framework. This keeps the stack simpler and the latency lower. Each data source connector is registered as a Claude tool with a name and description. Claude decides which tools to call based on the user query and the profile context injected into the system prompt.

**Multi-source synthesis via sequential tool calls.** For complex queries (e.g., "What are survival rates for stage III colorectal cancer in Noord-Brabant compared to the national average, and what does kanker.nl say about treatment?"), Claude calls multiple tools in sequence: first NKR-Cijfers for the statistics, then Cancer Atlas for the regional breakdown, then kanker.nl for patient-facing treatment information. It synthesizes the combined results into a single coherent response with per-claim citations.

**LiteLLM provider abstraction.** All LLM calls go through LiteLLM so the provider can be swapped from Claude to Ollama (local) without code changes. This gives us a local fallback for demo resilience and avoids hard coupling to a single provider.

**ChromaDB for vector search.** kanker.nl content and publication text are chunked and embedded into ChromaDB. This enables semantic retrieval for patient information queries where keyword matching is insufficient.

**SSE streaming from backend to frontend.** The FastAPI backend streams responses token-by-token to the Next.js frontend via Server-Sent Events, so users see answers appearing in real time rather than waiting for the full response to complete.

---

## Chat Orchestrator

### Session initialization

At session start, the system asks the user to identify their profile in Dutch:

> Welkom! Om u de beste informatie te geven, wil ik graag weten wie u bent:
> - Patient of naaste
> - Zorgprofessional
> - Beleidsmaker
> - (Overslaan)

The selected profile is stored in the session and injected into the Claude system prompt for every subsequent message. If the user skips, Claude infers the profile from conversation tone and vocabulary (e.g., use of medical terminology suggests a professional; emotional or first-person phrasing suggests a patient or loved one). The inferred profile can be revised as the conversation progresses.

### System prompt adaptation

The system prompt is dynamically composed based on the user profile. The following table defines how tone, source priority, and response depth vary per profile:

| Profile | Tone | Source priority | Depth |
|---|---|---|---|
| Patient / loved one | Warm, plain Dutch, empathetic | kanker.nl first, then statistics simplified | Summaries in accessible language, no jargon |
| Professional | Clinical, precise | NKR-Cijfers + publications + richtlijnendatabase | Full data tables, percentages, staging details |
| Policymaker | Analytical, comparative | Cancer Atlas + NKR trends + reports | Regional comparisons, trend analyses, aggregates |

For each profile, the system prompt includes explicit instructions on language register, which tools to prefer, and how much detail to include. The profile acts as a soft bias -- Claude can still use any source if the query demands it, but it prioritizes according to the table above.

### Guardrails

Guardrails are mapped directly to the hackathon judging criteria to ensure we score on every domain.

**Source citation on every response (Domain 1, Item 2).** Every claim in a response must include a citation with the source name and a URL. Citations are rendered as clickable source cards in the frontend. The system prompt instructs Claude to never make a statement without attributing it to a retrieved source.

**Trusted sources only -- no hallucinated URLs (Domain 1, Item 3).** Claude is instructed to only use information returned by its tools. It must not fabricate URLs, invent statistics, or reference sources outside the IKNL ecosystem. The tool responses include the canonical URL for each piece of content, and only those URLs may appear in citations.

**Graceful decline when no source is found (Domain 1, Item 5).** If none of the tools return relevant information for a query, Claude must explicitly say so and suggest where the user might find help (e.g., "Ik heb hier geen betrouwbare bron voor gevonden. Neem contact op met uw zorgverlener of kijk op kanker.nl."). It must not attempt to answer from general knowledge.

**Ethical filter -- no personal medical advice (Domain 3).** Claude must decline to provide personalized medical advice, diagnosis, or treatment recommendations. For patient-profile users asking about their own situation, it redirects to their huisarts or specialist. The system prompt includes explicit boundary language: "Je bent een informatieassistent, geen arts. Geef nooit persoonlijk medisch advies."
