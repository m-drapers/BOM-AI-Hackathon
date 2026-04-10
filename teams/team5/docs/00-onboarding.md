# Getting Started

BrabantHack_26 -- IKNL Med Tech track. A chat system connecting IKNL cancer information sources (kanker.nl, NKR-Cijfers, Cancer Atlas, publications, richtlijnendatabase) via Claude tool-use with RAG.

## Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm (for frontend)
- uv (for Python backend)
- Docker & Docker Compose (optional, for one-command startup)
- Anthropic API key (for Claude)
- Optional: Ollama (for local LLM fallback)

## Quick Start (Docker)

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
docker compose up
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs
```

## Quick Start (Local Development)

### Backend

```bash
cd backend
uv sync
uv run python -m ingestion.vectorize  # Build vector store (first time only)
uv run uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev  # http://localhost:3000
```

## Environment Variables

| Variable             | Required | Description                                                        |
| -------------------- | -------- | ------------------------------------------------------------------ |
| `ANTHROPIC_API_KEY`  | Yes      | Claude API key                                                     |
| `OPENAI_API_KEY`     | No       | For text-embedding-3-small (if not using local embeddings)         |
| `OLLAMA_BASE_URL`    | No       | Ollama URL for local LLM fallback (default: `http://localhost:11434`) |
| `EMBEDDING_PROVIDER` | No       | `"local"` or `"openai"` (default: `local`)                        |

## Data Sources

| Source | URL | Description | Docs |
| ------ | --- | ----------- | ---- |
| kanker.nl | [kanker.nl](https://www.kanker.nl) | National cancer info platform for patients & professionals | [sources/kanker.nl.md](../../sources/kanker.nl.md) |
| NKR-Cijfers | [nkr-cijfers.iknl.nl](https://nkr-cijfers.iknl.nl) | Netherlands Cancer Registry statistics | [sources/nkr-cijfers.nl.md](../../sources/nkr-cijfers.nl.md) |
| Cancer Atlas | [kankeratlas.iknl.nl](https://kankeratlas.iknl.nl) | Interactive geographic cancer incidence visualisation | [sources/kankeratlas.iknl.nl.md](../../sources/kankeratlas.iknl.nl.md) |
| Publications | [iknl.nl/onderzoek/publicaties](https://iknl.nl/onderzoek/publicaties) | Official IKNL research publications | [sources/publicaties.md](../../sources/publicaties.md) |
| Richtlijnendatabase | [richtlijnendatabase.nl](https://richtlijnendatabase.nl) | Dutch multidisciplinary clinical practice guidelines | [sources/richtlijnendatabase.nl.md](../../sources/richtlijnendatabase.nl.md) |

## Documentation Map

| Path | Contents |
| ---- | -------- |
| [`docs/01-architecture/`](../01-architecture/) | System architecture |
| [`docs/60-prd/`](../60-prd/) | Product requirements |
| [`docs/61-tsd/`](../61-tsd/) | Technical design specs |
| [`docs/success-criteria.md`](../success-criteria.md) | Hackathon judging criteria |
