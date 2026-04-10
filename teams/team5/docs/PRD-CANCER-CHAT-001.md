# PRD-CANCER-CHAT-001: Cancer Information Chat System

## Document Info

| Field          | Value                          |
|----------------|--------------------------------|
| PRD ID         | PRD-CANCER-CHAT-001            |
| Title          | Cancer Information Chat System |
| Status         | Draft                          |
| Author         | Team 5                         |
| Created        | 2026-04-10                     |
| Classification | Hackathon Prototype            |

---

## Problem Statement

People increasingly turn to general AI systems for cancer information because they are quick and easy to use, but the results are not always reliable. At the same time, trusted cancer knowledge from IKNL is spread across different platforms (kanker.nl, NKR-Cijfers, Cancer Atlas, richtlijnendatabase, publications), making it harder for patients, professionals, and policymakers to find accurate and consistent information. A user seeking survival rates must visit NKR-Cijfers, then cross-reference treatment options on kanker.nl, then look up regional patterns on the Cancer Atlas -- three separate websites, three different interfaces, no unified context. The result is fragmented access to information that should be connected.

## Objective

Build a chat-based interface that connects IKNL's distributed, trusted sources in a smarter, more accessible way using AI. The system must inform people faster, better, and more reliably by retrieving, synthesizing, and citing information from multiple authoritative sources through a single conversational interface -- while never fabricating or distorting medical information.

---

## Target Users

1. **Patients and loved ones** -- seeking understandable cancer information, treatment options, survival context, and practical guidance in plain Dutch. They need empathetic, jargon-free explanations grounded in kanker.nl content.

2. **Healthcare professionals** -- needing clinical data, statistics, stage distributions, survival rates, and guideline references. They expect precise numbers, confidence intervals, and direct links to authoritative sources.

3. **Policymakers** -- requiring regional comparisons, incidence trends, population-level insights, and geographic variation data. They need analytical framing with aggregated statistics and trend analyses.

---

## User Stories

### Patients and Loved Ones

**US-01: Ask about a specific cancer type.**
As a patient, I want to ask "Wat is borstkanker?" in plain language so that I receive an understandable explanation sourced from kanker.nl with a link to the original page.

**US-02: Understand survival rates simply.**
As a loved one, I want to ask about survival rates for a family member's diagnosis so that I receive a clear, compassionate explanation of what the statistics mean without being overwhelmed by raw numbers.

**US-03: Explore treatment options.**
As a patient recently diagnosed, I want to ask about treatment options for my cancer type so that I receive a summary of available treatments sourced from kanker.nl, with a clear note that I should discuss specifics with my doctor.

### Healthcare Professionals

**US-04: Look up stage distribution trends.**
As a healthcare professional, I want to query stage distribution data for a specific cancer type over time so that I can see how early detection patterns have changed, presented as a chart with precise percentages.

**US-05: Check clinical guidelines.**
As an oncologist, I want to ask about treatment protocols for a specific cancer type so that I receive relevant guideline excerpts with direct links to richtlijnendatabase.nl.

### Policymakers

**US-06: Compare regional incidence.**
As a policymaker, I want to compare cancer incidence across regions so that I can identify geographic areas with higher-than-expected rates using Cancer Atlas data, supported by a visual comparison.

### Cross-Cutting

**US-07: Ask a question that spans multiple sources.**
As any user, I want to ask a complex question like "Hoe vaak komt longkanker voor en wat zijn de behandelopties?" so that the system queries both NKR-Cijfers (incidence) and kanker.nl (treatments) and synthesizes a single coherent answer citing both sources.

**US-08: Switch profile mid-conversation.**
As a healthcare professional who initially selected "patient" mode, I want to switch my profile to "zorgprofessional" mid-conversation so that subsequent answers use clinical terminology and show full statistical detail without losing my conversation history.

**US-09: Give feedback on missing information.**
As any user, I want to flag when the system's answer is incomplete or misses relevant information so that IKNL can review gaps and improve their content coverage.

**US-10: Receive a safe decline for out-of-scope questions.**
As a patient asking for personal medical advice, I want the system to clearly decline and redirect me to my huisarts or specialist rather than attempting to answer a question it cannot reliably address.

---

## Functional Requirements

### Must Have (P0)

| ID   | Requirement | Details |
|------|-------------|---------|
| F-01 | Chat interface with streaming responses | SSE-based token streaming from FastAPI backend to Next.js frontend. Response latency under 1 second to first token. |
| F-02 | RAG retrieval from kanker.nl content | Semantic vector search over 2,816 pre-crawled kanker.nl pages stored in ChromaDB. Supports filtering by cancer type and section. |
| F-03 | NKR-Cijfers API integration | Live queries against the NKR-Cijfers public API for incidence, survival, prevalence, mortality, stage distribution, and conditional survival data. |
| F-04 | Source citations with URLs on every response | Every factual claim must include an inline citation linking to the specific source page or dataset. Citations rendered as clickable source cards below responses. |
| F-05 | User profile selection | Three profiles: Patient/naaste, Zorgprofessional, Beleidsmaker. Selectable at session start and changeable at any time during conversation. |
| F-06 | System prompt adaptation per profile | Dynamic system prompt composition adjusting tone, vocabulary, source priority, and response depth based on the active user profile. |
| F-07 | Decline with redirect when no source matches | When no connectors return relevant results, the system explicitly states it has no reliable information and suggests alternatives (kanker.nl, huisarts, specialist). |
| F-08 | Ethical filter -- no personal medical advice | The system declines personal treatment decisions, individual diagnosis, prognosis for specific cases, and medication recommendations. Redirects to healthcare providers. |

### Should Have (P1)

| ID   | Requirement | Details |
|------|-------------|---------|
| F-09 | Cancer Atlas geographic data integration | Connector to the Cancer Atlas Strapi API for Standardized Incidence Ratios (SIRs) at PC3 postcode level across 25 cancer groups. |
| F-10 | Inline data visualization | Render NKR-Cijfers statistics and Cancer Atlas SIRs as bar charts, line charts, or value indicators inline within chat messages using Recharts. |
| F-11 | Publications and reports search | Semantic search over indexed IKNL reports and scientific publications (Lancet, ESMO) stored in a separate ChromaDB collection. |
| F-12 | Feedback mechanism | Thumbs up/down per response plus a "Informatie mist?" text field for reporting content gaps. All feedback stored in SQLite with session and query context. |
| F-13 | Feedback export for IKNL review | CSV export endpoint (`GET /api/feedback/export`) providing all collected feedback for post-hackathon analysis. |

### Nice to Have (P2)

| ID   | Requirement | Details |
|------|-------------|---------|
| F-14 | Richtlijnendatabase integration | Pre-scraped clinical oncology guidelines from richtlijnendatabase.nl for the most common cancer types, stored in a third ChromaDB collection. |
| F-15 | Conversation memory across turns | Maintain context across multiple turns so follow-up questions like "En voor mannen?" work without repeating the full context. |
| F-16 | Export chat as PDF | Allow users to download the conversation including all sources and inline charts as a PDF document. |
| F-17 | Source comparison view | When multiple sources provide overlapping information, show a side-by-side comparison highlighting agreements and differences. |

---

## Non-Functional Requirements

| ID    | Requirement | Target |
|-------|-------------|--------|
| NF-01 | Streaming latency | Less than 1 second to first token |
| NF-02 | Primary language | Dutch (system responds in the language of the user's query, defaulting to Dutch) |
| NF-03 | Mobile support | Responsive design using Tailwind CSS; sidebar collapses to hamburger menu on small screens |
| NF-04 | Zero-infrastructure storage | ChromaDB (file-based in `data/chromadb/`), SQLite (`data/feedback.db`) -- no external database servers |
| NF-05 | Provider-agnostic LLM | Claude (Anthropic) as primary via LiteLLM abstraction; Ollama local fallback for demo resilience |
| NF-06 | One-command startup | Docker Compose configuration for running both frontend and backend with a single command |
| NF-07 | Trusted sources only | No web search tool available to the LLM; tool definitions limited to IKNL-approved connectors |

---

## Success Criteria

Mapped directly to the BrabantHack_26 IKNL judging domains.

### Domain 1: Information Integrity (5 items)

| # | Criterion | How the System Addresses It |
|---|-----------|----------------------------|
| 1 | The solution actually provides an answer | Claude tool-use queries multiple connectors in priority order; always attempts an answer before falling back to "no information found." |
| 2 | Clearly show source provenance and reliability | Every response includes source cards with specific URLs and reliability badges (Patienteninfo, Cijfers, Atlas, Publicatie, Richtlijn). |
| 3 | Only use trusted IKNL sources | Connector definitions restrict Claude to five approved sources. No web search tool is registered. |
| 4 | Avoid inventing or distorting medical information | RAG-grounded responses only. System prompt: "Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd." |
| 5 | Declines or redirects when it cannot provide an accurate answer | Explicit decline with redirect to kanker.nl or huisarts when no sources return relevant results. |

### Domain 2: Usability (3 items)

| # | Criterion | How the System Addresses It |
|---|-----------|----------------------------|
| 1 | Creates better pathways for different target groups | Three user profiles with adapted tone, source priority, and response depth. |
| 2 | Aligns with modern information-seeking behavior | Conversational chat with streaming responses and natural language queries in Dutch. |
| 3 | Helps users reach information faster | One interface replaces 4+ separate websites. One question triggers multi-source synthesis. |

### Domain 3: Ethics (1 item)

| # | Criterion | How the System Addresses It |
|---|-----------|----------------------------|
| 1 | Declines to answer in case of ethical issues | Ethical filter declines personal medical advice, diagnosis, and treatment recommendations. Redirects to healthcare providers. |

### Domain 4: Advanced Solution (3 items)

| # | Criterion | How the System Addresses It |
|---|-----------|----------------------------|
| 1 | Connects existing sources | All IKNL sources unified through Claude tool-use orchestration. Single questions can trigger multiple connectors. |
| 2 | Creatively improves understanding | Inline data visualization, profile-adapted explanations, and source reliability badges. |
| 3 | Demonstrates future potential | Connector interface (`SourceConnector`) makes adding sources trivial. LiteLLM enables provider swaps via config. |

### Bonus: Feedback Mechanism

| Criterion | How the System Addresses It |
|-----------|----------------------------|
| User feedback collection | Thumbs up/down plus "Informatie mist?" text input per response. Stored in SQLite with full context. CSV export for IKNL review. |

---

## Out of Scope

- **Real-time data updates from NKR** -- the system uses the public API which reflects published registry data, not live feeds.
- **User authentication** -- no login, no user accounts, no session persistence across browser sessions.
- **Multi-language beyond Dutch/English** -- the system supports Dutch as primary and English as fallback. No other languages.
- **Production deployment** -- this is a hackathon prototype. No production hosting, scaling, or monitoring.
- **HIPAA/AVG compliance beyond prototype level** -- no personal health data is collected or stored. Feedback contains only query text and ratings.
- **Live web scraping at query time** -- all content retrieval uses pre-indexed data or public APIs.

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Anthropic Claude API | External service | Primary LLM provider. Requires API key. |
| NKR-Cijfers API | Public REST API | `https://api.nkr-cijfers.iknl.nl/api/` -- no authentication required. |
| Cancer Atlas API | Public REST API | Strapi backend at `iknl-atlas-strapi-prod.azurewebsites.net` -- no authentication required. |
| kanker.nl pre-crawled dataset | Local file | `data/kanker_nl_pages_all.json` -- 2,816 pages, provided in repository. |
| ChromaDB | Local library | File-based vector store, no server process required. |
| Ollama (optional) | Local service | Fallback LLM for demo resilience when Anthropic API is unavailable. |

---

## Architecture Overview

```
+-----------------------------------------------------------+
|                    Next.js Frontend                        |
|  Chat UI (streaming) | Source Cards | Data Viz (Recharts)  |
+-----------------------------+-----------------------------+
                              | SSE / streaming
+-----------------------------+-----------------------------+
|                    FastAPI Backend                         |
|  +-----------------------------------------------------+  |
|  |              Chat Orchestrator                       |  |
|  |  - User profiling (profile selection + intent)       |  |
|  |  - Claude native tool-use (primary)                  |  |
|  |  - LiteLLM provider abstraction (Ollama fallback)    |  |
|  +------+--------+--------+--------+------------------+  |
|         |        |        |        |                      |
|  +------+--+ +---+----+ +-+-----+ +--------+---------+   |
|  |kanker.nl| |NKR-Cijf.| |Atlas | |Publications      |   |
|  |Vector   | |API      | |API   | |PDF/Text Search   |   |
|  |Search   | |Connector| |Conn. | |                  |   |
|  +------+--+ +---------+ +------+ +------------------+   |
|         |                                                  |
|  +------+----------------+                                 |
|  |  ChromaDB (file-based)|                                 |
|  +-----------------------+                                 |
+-----------------------------------------------------------+
```

---

## Appendix: Data Source Summary

| Source | Content Type | Volume | Access Method | Profile Affinity |
|--------|-------------|--------|---------------|-----------------|
| kanker.nl | Patient information pages | 2,816 pages, 88 cancer types | ChromaDB vector search | Patient/naaste |
| NKR-Cijfers | Cancer registry statistics | 6 data pages, filters by period/sex/age/region/stage | REST API (POST) | Professional, Policymaker |
| Cancer Atlas | Regional incidence ratios | 25 cancer groups, ~890 PC3 areas | REST API (GET) | Policymaker |
| Publications | Reports and papers | 5 documents (3 NL, 2 EN) | ChromaDB vector search | Professional |
| Richtlijnendatabase | Clinical guidelines | Stretch goal -- top 6 cancer types | ChromaDB vector search | Professional |
