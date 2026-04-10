# Cancer Information Chat System

Hackathon project (BrabantHack_26, IKNL Med Tech track) that connects IKNL's distributed trusted cancer information sources into a unified chat experience with full citation provenance.

## Quick Start

Head to [00-onboarding/](./00-onboarding/) for environment setup and first-run instructions.

---

## Documentation Map

### [00-onboarding/](./00-onboarding/) -- Getting Started

Setup guides, environment configuration, and first-run instructions.

### [01-architecture/](./01-architecture/) -- System Architecture

Architecture decisions, component diagrams, and data flow documentation.

### [40-implementation-plans/](./40-implementation-plans/) -- Implementation Plans

Step-by-step plans for building each part of the system.

### [60-prd/](./60-prd/) -- Product Requirement Documents

Product requirements, user stories, and feature definitions.

### [61-tsd/](./61-tsd/) -- Technical Design Specifications

Detailed technical designs for individual components.

### [success-criteria.md](./success-criteria.md) -- Hackathon Judging Criteria

The four scoring domains: Information Integrity, Usability, Ethics, and Advanced Solution. Maps directly to guardrails in the chat orchestrator.

### [superpowers/specs/](./superpowers/specs/) -- Design Specs

Brainstorming and design exploration documents:

- [cancer-info-chat-design](./superpowers/specs/2026-04-10-cancer-info-chat-design.md) -- End-to-end system design: architecture, chat orchestrator, user profiling, guardrails, and multi-source synthesis.
- [frontend-stack-design](./superpowers/specs/2026-04-10-frontend-stack-design.md) -- Tech stack rationale, frontend components, SSE streaming, and UI layout.
- [source-connectors-design](./superpowers/specs/2026-04-10-source-connectors-design.md) -- Connector interface, per-source implementation (kanker.nl, NKR-Cijfers, Cancer Atlas, publications).

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.11+ |
| LLM | Claude (Anthropic) via LiteLLM, Ollama fallback |
| Orchestration | Claude native tool-use |
| Vector store | ChromaDB |
| Dev tooling | uv, pnpm, Docker Compose |

## Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| kanker.nl | Vector search (ChromaDB) | Patient-facing cancer information |
| NKR-Cijfers | REST API | Cancer registry statistics |
| Cancer Atlas | REST API | Regional cancer data and maps |
| Publications | PDF/text search | Research papers and reports |
| Richtlijnendatabase | TBD | Clinical guidelines |

## Target Groups

- **Patients and loved ones** -- plain-language answers from kanker.nl
- **Healthcare professionals** -- clinical data from NKR, publications, guidelines
- **Policymakers** -- regional comparisons and trend analyses from Cancer Atlas
