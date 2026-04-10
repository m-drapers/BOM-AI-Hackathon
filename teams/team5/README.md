# Team 5 — Cancer Information Chat

> **A solution to inform people faster, better, and more reliably by connecting IKNL's distributed, trusted sources in a smarter, more accessible, and future-proof way.**

## The Problem

People increasingly turn to general AI for cancer information, but the results are unreliable. Meanwhile, IKNL's trusted knowledge is spread across 5+ different platforms — patients, professionals, and policymakers must visit multiple websites to get a complete picture.

## Our Solution

A chat-based interface that connects all of IKNL's trusted sources into a single conversation. Ask a question in natural language, get an answer grounded in real IKNL data — with full source citations.

The system adapts to who you are:
- **Patients** get warm, plain-Dutch explanations from kanker.nl
- **Professionals** get clinical data, statistics, and guidelines
- **Policymakers** get regional comparisons and trend analyses

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
│  │  Claude native tool-use + profile adaptation     │    │
│  └──────┬──────────┬──────────┬──────────┬─────────┘    │
│  ┌──────┴───┐ ┌────┴────┐ ┌──┴───┐ ┌───┴──────────┐   │
│  │kanker.nl │ │NKR-Cijf.│ │Atlas │ │Publications  │   │
│  │ 2816 pgs │ │  Stats  │ │Region│ │  Reports     │   │
│  └──────────┘ └─────────┘ └──────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone and enter team directory
cd teams/team5

# Copy environment config
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Option 1: Docker (recommended)
docker compose up

# Option 2: Local development
cd backend && uv sync && uv run uvicorn main:app --reload --port 8000
cd ../frontend && pnpm install && pnpm dev
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

## Data Sources Connected

| Source | What it provides | How we use it |
|--------|-----------------|---------------|
| [kanker.nl](https://kanker.nl) | Patient cancer information (2,816 pages) | RAG vector search via ChromaDB |
| [NKR-Cijfers](https://nkr-cijfers.iknl.nl) | Cancer registry statistics (1961-2025) | Live API queries for incidence, survival, staging |
| [Cancer Atlas](https://kankeratlas.iknl.nl) | Regional cancer variation (890 postcodes) | Live API for geographic SIR data |
| IKNL Publications | 3 reports + 5 scientific papers | RAG vector search via ChromaDB |

## Key Features

- **Source provenance on every response** — clickable citations with reliability badges
- **Profile-adaptive** — tone, source priority, and depth adjust per user type
- **Inline data visualization** — charts for statistics, color-coded regional data
- **Ethical guardrails** — declines personal medical advice, redirects to huisarts
- **Feedback mechanism** — thumbs up/down + "informatie mist?" for IKNL review

## Tech Stack

Python 3.11 + FastAPI | Next.js 14 + TypeScript + Tailwind | Claude (Anthropic) | ChromaDB | LiteLLM

## Team

Team 5 — BrabantHack_26

## Documentation

See [docs/](./docs/) for full architecture, PRD, TSD, and implementation plans.
