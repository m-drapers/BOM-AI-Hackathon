# Cancer Information Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a chat system that connects IKNL's trusted cancer information sources (kanker.nl, NKR-Cijfers, Cancer Atlas, publications) into a unified conversational interface with RAG retrieval, inline data visualization, and user-profile adaptation.

**Architecture:** FastAPI backend with Claude native tool-use orchestrating 5 source connectors (kanker.nl vector search, NKR-Cijfers API, Cancer Atlas API, publications vector search, richtlijnendatabase stretch). Next.js frontend with streaming chat, source cards, and inline charts. ChromaDB for vector storage, SQLite for feedback.

**Tech Stack:** Python 3.11+, FastAPI, ChromaDB, LiteLLM, Anthropic SDK, PyMuPDF, sentence-transformers | Next.js 14, TypeScript, Tailwind CSS, Recharts

---

## File Structure

### Backend
- `backend/pyproject.toml` — Python project config with uv
- `backend/config.py` — Settings via pydantic-settings, env vars
- `backend/models.py` — Pydantic models (ChatRequest, ChatMessage, SourceResult, Citation, etc.)
- `backend/connectors/base.py` — SourceConnector ABC + SourceResult + Citation
- `backend/connectors/kanker_nl.py` — kanker.nl ChromaDB vector search
- `backend/connectors/nkr_cijfers.py` — NKR-Cijfers REST API wrapper
- `backend/connectors/cancer_atlas.py` — Cancer Atlas API wrapper
- `backend/connectors/publications.py` — Publications ChromaDB vector search
- `backend/ingestion/sitemap_builder.py` — kanker.nl JSON → sitemap tree
- `backend/ingestion/vectorize.py` — Chunking + embedding pipeline
- `backend/ingestion/pdf_extractor.py` — PDF text extraction
- `backend/orchestrator.py` — Chat orchestrator with Claude tool-use
- `backend/main.py` — FastAPI app, SSE endpoint, feedback endpoints
- `backend/tests/test_models.py`
- `backend/tests/test_connectors/test_kanker_nl.py`
- `backend/tests/test_connectors/test_nkr_cijfers.py`
- `backend/tests/test_connectors/test_cancer_atlas.py`
- `backend/tests/test_connectors/test_publications.py`
- `backend/tests/test_orchestrator.py`
- `backend/tests/test_api.py`

### Frontend
- `frontend/package.json`
- `frontend/app/page.tsx` — Main chat page
- `frontend/app/layout.tsx` — Root layout
- `frontend/components/ChatMessage.tsx`
- `frontend/components/SourceCard.tsx`
- `frontend/components/DataChart.tsx`
- `frontend/components/FeedbackWidget.tsx`
- `frontend/components/ProfileSelector.tsx`
- `frontend/lib/chat-client.ts` — SSE streaming client
- `frontend/lib/types.ts` — TypeScript interfaces

### Infrastructure
- `docker-compose.yml`
- `.env.example`

---

## PART 1: BACKEND CORE (Tasks 1-4)

---

### Task 1: Backend Project Setup

**Files to create:**
- `backend/pyproject.toml`
- `backend/config.py`
- `backend/tests/__init__.py`
- `backend/connectors/__init__.py`
- `backend/ingestion/__init__.py`

**Steps:**

- [ ] **1.1** Create `backend/pyproject.toml` with all dependencies:

```toml
[project]
name = "cancer-info-chat"
version = "0.1.0"
description = "IKNL Cancer Information Chat System — hackathon prototype"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "anthropic>=0.49.0",
    "litellm>=1.30.0",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
    "pymupdf>=1.24.0",
    "pydantic-settings>=2.2.0",
    "httpx>=0.27.0",
    "sse-starlette>=2.0.0",
    "aiosqlite>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **1.2** Create `backend/config.py` with Settings class:

```python
"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration. All values can be overridden via env vars or .env file."""

    # LLM
    ANTHROPIC_API_KEY: str = ""
    LLM_PROVIDER: str = "anthropic"  # "anthropic" | "ollama"
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Embeddings
    EMBEDDING_MODEL: str = "multilingual-e5-large"

    # Storage
    CHROMADB_PATH: str = "data/chromadb"
    FEEDBACK_DB_PATH: str = "data/feedback.db"

    # Data sources
    KANKER_NL_JSON_PATH: str = "data/kanker_nl_pages_all.json"
    PUBLICATIONS_DIR: str = "data/reports"
    SCIENTIFIC_PUBLICATIONS_DIR: str = "data/scientific_publications"
    SITEMAP_PATH: str = "data/sitemap.json"

    # NKR-Cijfers API
    NKR_API_BASE_URL: str = "https://api.nkr-cijfers.iknl.nl/api"

    # Cancer Atlas API
    CANCER_ATLAS_URL: str = "https://kankeratlas.iknl.nl"
    CANCER_ATLAS_STRAPI_URL: str = "https://iknl-atlas-strapi-prod.azurewebsites.net"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **1.3** Create empty `__init__.py` files for packages:

```bash
touch backend/tests/__init__.py
touch backend/connectors/__init__.py
touch backend/ingestion/__init__.py
```

- [ ] **1.4** Install dependencies:

```bash
cd backend && uv sync
```

- [ ] **1.5** Verify installation:

```bash
cd backend && uv run python -c "import fastapi, anthropic, chromadb, sentence_transformers, fitz; print('All imports OK')"
```

- [ ] **1.6** Commit: `git add backend/pyproject.toml backend/config.py backend/tests/__init__.py backend/connectors/__init__.py backend/ingestion/__init__.py && git commit -m "feat(backend): project setup with pyproject.toml and config"`

---

### Task 2: Data Models

**Files to create:**
- `backend/models.py`
- `backend/tests/test_models.py`

**Steps:**

- [ ] **2.1** Write `backend/tests/test_models.py` (tests first):

```python
"""Tests for Pydantic data models."""

import pytest
from datetime import datetime, timezone

from models import (
    ChatMessage,
    ChatRequest,
    Citation,
    SourceCard,
    ChartData,
    FeedbackEntry,
    SourceResult,
    SessionContext,
)


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(
            message="Hoe vaak komt borstkanker voor?",
            session_id="abc-123",
            profile="patient",
        )
        assert req.message == "Hoe vaak komt borstkanker voor?"
        assert req.profile == "patient"
        assert req.history == []

    def test_invalid_profile_rejected(self):
        with pytest.raises(Exception):
            ChatRequest(
                message="test",
                session_id="abc",
                profile="invalid_profile",
            )

    def test_with_history(self):
        req = ChatRequest(
            message="En de overlevingskansen?",
            session_id="abc-123",
            profile="professional",
            history=[
                ChatMessage(role="user", content="Hoe vaak komt longkanker voor?"),
                ChatMessage(role="assistant", content="Longkanker komt..."),
            ],
        )
        assert len(req.history) == 2
        assert req.history[0].role == "user"


class TestSourceResult:
    def test_construction(self):
        result = SourceResult(
            data={"incidence": 14000, "year": 2023},
            summary="In 2023 werden er 14.000 nieuwe gevallen geregistreerd.",
            sources=[
                Citation(
                    url="https://nkr-cijfers.iknl.nl/",
                    title="NKR Incidentiecijfers",
                    reliability="official",
                )
            ],
            visualizable=True,
        )
        assert result.visualizable is True
        assert len(result.sources) == 1
        assert result.sources[0].reliability == "official"

    def test_empty_data(self):
        result = SourceResult(
            data=None,
            summary="Geen resultaten gevonden.",
            sources=[],
            visualizable=False,
        )
        assert result.data is None


class TestFeedbackEntry:
    def test_timestamp_default(self):
        entry = FeedbackEntry(
            session_id="sess-1",
            message_id="msg-1",
            rating="positive",
            query="test query",
            sources_tried=["kanker_nl"],
        )
        assert entry.timestamp is not None
        assert isinstance(entry.timestamp, datetime)

    def test_negative_with_comment(self):
        entry = FeedbackEntry(
            session_id="sess-1",
            message_id="msg-1",
            rating="negative",
            comment="Ik miste informatie over bijwerkingen.",
            query="Wat zijn de behandelingen voor borstkanker?",
            sources_tried=["kanker_nl", "nkr_cijfers"],
            profile="patient",
        )
        assert entry.rating == "negative"
        assert entry.comment is not None
        assert len(entry.sources_tried) == 2


class TestChartData:
    def test_line_chart(self):
        chart = ChartData(
            type="line",
            title="Borstkanker incidentie 2015-2023",
            data=[
                {"year": 2015, "count": 14500},
                {"year": 2023, "count": 15200},
            ],
            x_key="year",
            y_key="count",
            unit="gevallen",
        )
        assert chart.type == "line"
        assert len(chart.data) == 2

    def test_value_chart(self):
        chart = ChartData(
            type="value",
            title="5-jaarsoverleving",
            data=[{"value": 87.3}],
            x_key="label",
            y_key="value",
        )
        assert chart.unit is None


class TestSourceCard:
    def test_construction(self):
        card = SourceCard(
            source="kanker_nl",
            url="https://www.kanker.nl/kankersoorten/borstkanker/algemeen",
            reliability="patient-info",
            contributed=True,
        )
        assert card.contributed is True


class TestSessionContext:
    def test_defaults(self):
        ctx = SessionContext(
            session_id="sess-1",
            profile="policymaker",
            history=[],
        )
        assert ctx.inferred_intent is None

    def test_with_intent(self):
        ctx = SessionContext(
            session_id="sess-1",
            profile="professional",
            history=[ChatMessage(role="user", content="test")],
            inferred_intent="statistical",
        )
        assert ctx.inferred_intent == "statistical"
```

- [ ] **2.2** Run tests to verify they fail (models.py does not exist yet):

```bash
cd backend && uv run pytest tests/test_models.py -v 2>&1 | head -20
# Expected: ModuleNotFoundError or ImportError
```

- [ ] **2.3** Write `backend/models.py` with all Pydantic models:

```python
"""Pydantic data models for the Cancer Information Chat system.

Covers request/response schemas, connector results, feedback, and session state.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --- Chat ---


class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    message: str
    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage] = []


# --- Sources ---


class Citation(BaseModel):
    """A single source citation attached to a connector result."""

    url: str
    title: str
    reliability: str  # "official", "peer-reviewed", "patient-info", "scraped"


class SourceCard(BaseModel):
    """Metadata for a source card displayed in the frontend."""

    source: str  # connector name: kanker_nl, nkr_cijfers, cancer_atlas, publications
    url: str
    reliability: str
    contributed: bool  # True if the source contributed content to the response


class SourceResult(BaseModel):
    """Returned by every connector after a query."""

    data: Any = None  # structured data, text passages, or None on error
    summary: str  # human-readable summary for Claude to narrate
    sources: list[Citation] = []
    visualizable: bool = False  # hint to frontend for chart rendering


# --- Visualization ---


class ChartData(BaseModel):
    """Structured chart data sent to the frontend for inline visualization."""

    type: Literal["line", "bar", "value"]
    title: str
    data: list[dict]  # Recharts-compatible data array
    x_key: str
    y_key: str
    unit: Optional[str] = None


# --- Feedback ---


class FeedbackEntry(BaseModel):
    """User feedback on a single assistant response."""

    session_id: str
    message_id: str
    rating: Literal["positive", "negative"]
    comment: Optional[str] = None
    query: str
    sources_tried: list[str]
    profile: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Session ---


class SessionContext(BaseModel):
    """Internal state tracked per chat session."""

    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage] = []
    inferred_intent: Optional[str] = None  # informational, statistical, geographic, clinical
```

- [ ] **2.4** Run tests and verify all pass:

```bash
cd backend && uv run pytest tests/test_models.py -v
# Expected: 11 passed
```

- [ ] **2.5** Commit: `git add backend/models.py backend/tests/test_models.py && git commit -m "feat(backend): Pydantic data models with tests"`

---

### Task 3: Connector Base Interface

**Files to create:**
- `backend/connectors/base.py`

**Steps:**

- [ ] **3.1** Write `backend/connectors/base.py` with the SourceConnector ABC:

```python
"""Base interface for all data source connectors.

Every connector implements the SourceConnector ABC. The orchestrator
discovers connectors by their `name` and `description` attributes
and presents them to Claude as callable tools.

Re-exports SourceResult and Citation from models for convenience,
so connector implementations can do:
    from connectors.base import SourceConnector, SourceResult, Citation
"""

from abc import ABC, abstractmethod

from models import Citation, SourceResult

# Re-export for convenience
__all__ = ["SourceConnector", "SourceResult", "Citation"]


class SourceConnector(ABC):
    """Abstract base class for all data source connectors.

    Attributes:
        name: Machine-readable connector name (e.g. "kanker_nl").
        description: Plain-language description that Claude reads to decide
                     when to use this connector.
    """

    name: str
    description: str

    @abstractmethod
    async def query(self, **params) -> SourceResult:
        """Execute a query against this data source.

        Every implementation must:
        1. Catch its own transport and parsing errors.
        2. Return a SourceResult with an empty `data` field and a descriptive
           `summary` on failure, so Claude can relay the problem to the user
           instead of crashing.

        Args:
            **params: Connector-specific query parameters.

        Returns:
            SourceResult with data, summary, source citations, and
            a visualizable hint.
        """
        ...
```

- [ ] **3.2** Verify the import chain works:

```bash
cd backend && uv run python -c "from connectors.base import SourceConnector, SourceResult, Citation; print('Imports OK')"
```

- [ ] **3.3** Commit: `git add backend/connectors/base.py && git commit -m "feat(backend): SourceConnector ABC base interface"`

---

### Task 4: kanker.nl Ingestion Pipeline

**Files to create:**
- `backend/ingestion/sitemap_builder.py`
- `backend/ingestion/vectorize.py`

**Steps:**

- [ ] **4.1** Write `backend/ingestion/sitemap_builder.py`:

```python
"""Build a structured sitemap from the pre-crawled kanker.nl JSON.

Reads data/kanker_nl_pages_all.json (2,816 pages, 87 cancer types)
and produces data/sitemap.json with cleaned, deduplicated entries
containing kankersoort, section, url, title, and text_length metadata.

Run directly:
    cd backend && uv run python -m ingestion.sitemap_builder
"""

import json
import re
import sys
from pathlib import Path

# ---- Configuration ----

# Resolve paths relative to the backend/ directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"
INPUT_PATH = DATA_DIR / "kanker_nl_pages_all.json"
OUTPUT_PATH = DATA_DIR / "sitemap.json"

CANONICAL_PREFIX = "https://www.kanker.nl/"

# The six canonical sections on kanker.nl. Anything else is mapped to one
# of these, or falls into "overig" if no match.
CANONICAL_SECTIONS = {
    "algemeen",
    "diagnose",
    "onderzoeken",
    "behandelingen",
    "gevolgen",
    "na-de-uitslag",
}

# Section name aliases found in the crawled data.  Each maps to one of the
# six canonical sections above.
SECTION_ALIAS_MAP: dict[str, str] = {
    # behandelingen variants
    "behandeling": "behandelingen",
    "behandeling-en-bijwerkingen": "behandelingen",
    "behandeling-van-borstkanker": "behandelingen",
    "behandeling-van-kwaadaardige-trofoblastziekten": "behandelingen",
    "behandelingen-bij-baarmoederhalskanker": "behandelingen",
    "behandelingen-bij-galwegkanker": "behandelingen",
    # onderzoeken variants
    "onderzoek": "onderzoeken",
    "onderzoek-en-diagnose": "onderzoeken",
    "onderzoeken-bij-zaadbalkanker": "onderzoeken",
    "onderzoeken-bij-borstkanker": "onderzoeken",
    # diagnose variants
    "de-diagnose-melanoom": "diagnose",
    "de-diagnose-borstkanker": "diagnose",
    "de-diagnose-baarmoederhalskanker": "diagnose",
    "de-diagnose-peniskanker": "diagnose",
    "de-diagnose-maagkanker": "diagnose",
    "de-diagnose-anuskanker": "diagnose",
    "diagnose-eierstokkanker": "diagnose",
    "de-uitslag": "diagnose",
    # na-de-uitslag variants
    "na-de-uitslag-baarmoederhalskanker": "na-de-uitslag",
    "na-de-uitslag-leukemie": "na-de-uitslag",
    "na-de-uitslag-leverkanker": "na-de-uitslag",
    "na-de-uitslag-merkelcelcarcinoom": "na-de-uitslag",
    "na-de-uitslag-oogkanker": "na-de-uitslag",
    "na-de-uitslag-primaire-tumor-onbekend": "na-de-uitslag",
    "na-de-uitslag-schaamlipkanker": "na-de-uitslag",
    "na-de-uitslag-vaginakanker": "na-de-uitslag",
    "na-de-diagnose-net": "na-de-uitslag",
    "leven-met-een-huidlymfoom": "na-de-uitslag",
    # gevolgen - no aliases found in the data so far
}

# Kankersoort slug normalization: old slug -> canonical slug.
# The crawled data contains pages under both the old and new name for
# two cancer types.  We keep the longer (newer) canonical slug and
# rewrite the old one.
KANKERSOORT_CANONICAL_MAP: dict[str, str] = {
    "botkanker": "botkanker-botsarcoom",
    "wekedelentumoren": "wekedelentumoren-wekedelensarcomen",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to the canonical https://www.kanker.nl/ prefix
    and strip trailing slashes."""
    url = url.strip().rstrip("/")
    if url.startswith("https://kanker.nl/"):
        url = url.replace("https://kanker.nl/", CANONICAL_PREFIX, 1)
    return url


def parse_url_parts(url: str) -> tuple[str, str, str]:
    """Extract (kankersoort, section, page_slug) from a normalized kanker.nl URL.

    Returns ("", "", slug) for URLs that don't match the expected pattern.
    """
    path = url.replace(CANONICAL_PREFIX + "kankersoorten/", "")
    parts = path.split("/")

    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], ""
    elif len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


def extract_title(text: str) -> str:
    """Extract the page title from the first non-empty line of the text."""
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("Deze informatie"):
            return line[:200]
    return "Onbekend"


def build_sitemap() -> list[dict]:
    """Load the crawled JSON, clean, deduplicate, and return sitemap entries."""
    print(f"Loading {INPUT_PATH} ...")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        raw: dict[str, dict] = json.load(f)
    print(f"  Loaded {len(raw)} pages")

    # --- Pass 1: Normalize URLs, skip error pages, build candidate list ---
    candidates: dict[str, dict] = {}  # normalized_url -> entry
    skipped_errors = 0
    skipped_dupes = 0

    for url, page in raw.items():
        text = page.get("text", "")

        # Skip 503 error pages
        if "Error 503" in text[:200] or "Backend fetch failed" in text[:200]:
            skipped_errors += 1
            continue

        # Skip very short pages (likely broken)
        if len(text.strip()) < 30:
            skipped_errors += 1
            continue

        norm_url = normalize_url(url)

        # Deduplicate: keep the version with the most content
        if norm_url in candidates:
            skipped_dupes += 1
            if len(text) > len(candidates[norm_url]["text"]):
                candidates[norm_url]["text"] = text
            continue

        kankersoort_raw, section_raw, _ = parse_url_parts(norm_url)

        # Normalize kankersoort slug
        kankersoort = KANKERSOORT_CANONICAL_MAP.get(kankersoort_raw, kankersoort_raw)

        # Normalize section to one of the 6 canonical sections
        if section_raw in CANONICAL_SECTIONS:
            section = section_raw
        elif section_raw in SECTION_ALIAS_MAP:
            section = SECTION_ALIAS_MAP[section_raw]
        else:
            section = section_raw if section_raw else "algemeen"

        title = extract_title(text)

        candidates[norm_url] = {
            "kankersoort": kankersoort,
            "section": section,
            "url": norm_url,
            "title": title,
            "text": text,
            "text_length": len(text),
        }

    print(f"  Skipped {skipped_errors} error/broken pages")
    print(f"  Merged {skipped_dupes} duplicate URLs")

    # --- Pass 2: Deduplicate content across kankersoort aliases ---
    # For botkanker/botkanker-botsarcoom and wekedelentumoren/wekedelentumoren-wekedelensarcomen,
    # pages may exist under both slugs with identical content.  Keep only the
    # canonical (longer) slug version.
    final: dict[str, dict] = {}
    deduped_alias = 0

    for norm_url, entry in candidates.items():
        # Check if there's an equivalent under the canonical slug
        skip = False
        for old_slug, new_slug in KANKERSOORT_CANONICAL_MAP.items():
            old_prefix = f"{CANONICAL_PREFIX}kankersoorten/{old_slug}/"
            new_prefix = f"{CANONICAL_PREFIX}kankersoorten/{new_slug}/"
            if norm_url.startswith(old_prefix):
                canonical_url = norm_url.replace(old_prefix, new_prefix, 1)
                if canonical_url in candidates:
                    # Canonical version exists — skip the old-slug version
                    deduped_alias += 1
                    skip = True
                    break
                else:
                    # Old slug only — rewrite the URL to the canonical slug
                    entry = {**entry, "url": canonical_url, "kankersoort": new_slug}
                    norm_url = canonical_url
                    break
        if not skip:
            final[norm_url] = entry

    print(f"  Deduped {deduped_alias} alias pages (botkanker/wekedelentumoren)")

    # Strip the raw text from the sitemap output (it's only needed for dedup)
    # but keep text_length as metadata
    sitemap_entries = []
    for entry in final.values():
        sitemap_entries.append({
            "kankersoort": entry["kankersoort"],
            "section": entry["section"],
            "url": entry["url"],
            "title": entry["title"],
            "text_length": entry["text_length"],
        })

    # Sort for deterministic output
    sitemap_entries.sort(key=lambda e: (e["kankersoort"], e["section"], e["url"]))

    print(f"  Final sitemap: {len(sitemap_entries)} pages")
    print(f"  Unique kankersoorten: {len(set(e['kankersoort'] for e in sitemap_entries))}")
    return sitemap_entries


def main():
    sitemap = build_sitemap()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sitemap, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {OUTPUT_PATH} ({len(sitemap)} entries)")


if __name__ == "__main__":
    main()
```

- [ ] **4.2** Write `backend/ingestion/vectorize.py`:

```python
"""Chunking + embedding pipeline for kanker.nl content and publications.

Creates two ChromaDB collections:
  - "kanker_nl"     — kanker.nl patient information pages
  - "publications"  — PDF reports and scientific papers

Run directly:
    cd backend && uv run python -m ingestion.vectorize
"""

import json
import os
import sys
from pathlib import Path

import chromadb
import fitz  # PyMuPDF

# ---- Configuration ----

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"
KANKER_NL_JSON = DATA_DIR / "kanker_nl_pages_all.json"
SITEMAP_JSON = DATA_DIR / "sitemap.json"
CHROMADB_PATH = DATA_DIR / "chromadb"
REPORTS_DIR = DATA_DIR / "reports"
SCIENTIFIC_DIR = DATA_DIR / "scientific_publications"

CHUNK_SIZE = 500  # approximate tokens (we use words as proxy: ~1.3 tokens/word for Dutch)
CHUNK_OVERLAP = 50
WORDS_PER_CHUNK = 375  # ~500 tokens / 1.33 tokens per Dutch word
WORDS_OVERLAP = 38  # ~50 tokens

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

# Publication metadata lookup — maps filename stems to metadata
PUBLICATION_META: dict[str, dict] = {
    "rapport_manvrouwverschillenbij-kanker_definitief2": {
        "source_type": "report",
        "title": "Man-vrouwverschillen bij kanker",
        "language": "nl",
        "topic": "Sekseverschillen in incidentie en uitkomsten",
    },
    "rapport_UItgezaaide-kanker_2025_cijfers-inzichten-en-uitdagingen": {
        "source_type": "report",
        "title": "Uitgezaaide kanker 2025",
        "language": "nl",
        "topic": "Cijfers, inzichten en uitdagingen bij uitgezaaide kanker",
    },
    "trendrapport_darmkanker_def": {
        "source_type": "report",
        "title": "Trendrapport darmkanker",
        "language": "nl",
        "topic": "Langetermijntrends bij darmkanker",
    },
    "comorbidities_medication_use_and_overall_survival_in_eight_cancers": {
        "source_type": "publication",
        "title": "Comorbidities and survival in 8 cancers",
        "language": "en",
        "topic": "Impact of comorbid conditions on cancer survival (The Lancet)",
    },
    "head_and_neck_cancers_survival_in_europe_taiwan_and_japan": {
        "source_type": "publication",
        "title": "Head and neck cancers survival in Europe, Taiwan and Japan",
        "language": "en",
        "topic": "International comparison of head and neck cancer survival",
    },
    "ovarian_cancer_recurrence_prediction": {
        "source_type": "publication",
        "title": "Ovarian cancer recurrence prediction",
        "language": "en",
        "topic": "ML model for ovarian cancer outcomes (ESMO)",
    },
    "trends_and_variations_in_the_treatment_of_stage_I_III_non_small_cell_lung_cancer": {
        "source_type": "publication",
        "title": "Trends in treatment of stage I-III NSCLC",
        "language": "en",
        "topic": "Treatment trends for non-small cell lung cancer",
    },
    "trends_and_variations_in_the_treatment_of_stage_I_III_small_cell_lung_cancer": {
        "source_type": "publication",
        "title": "Trends in treatment of stage I-III SCLC",
        "language": "en",
        "topic": "Treatment trends for small cell lung cancer",
    },
}


def chunk_text(text: str, words_per_chunk: int = WORDS_PER_CHUNK, overlap: int = WORDS_OVERLAP) -> list[str]:
    """Split text into overlapping chunks of approximately `words_per_chunk` words.

    Uses word boundaries to avoid splitting mid-sentence where possible.
    Falls back to a simple word-count split — good enough for a hackathon.
    """
    words = text.split()
    if len(words) <= words_per_chunk:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunk_words = words[start:end]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
        start += words_per_chunk - overlap

    return chunks


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF using PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def get_embedding_function():
    """Create a ChromaDB-compatible embedding function using sentence-transformers."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )


def ingest_kanker_nl(client: chromadb.ClientAPI, ef):
    """Ingest kanker.nl pages into the 'kanker_nl' ChromaDB collection."""
    print("\n=== Ingesting kanker.nl content ===")

    # Load sitemap for metadata
    if not SITEMAP_JSON.exists():
        print(f"ERROR: {SITEMAP_JSON} not found. Run sitemap_builder.py first.")
        sys.exit(1)

    with open(SITEMAP_JSON, "r", encoding="utf-8") as f:
        sitemap: list[dict] = json.load(f)

    # Build URL -> metadata lookup
    url_meta = {entry["url"]: entry for entry in sitemap}

    # Load the full page content
    with open(KANKER_NL_JSON, "r", encoding="utf-8") as f:
        pages: dict[str, dict] = json.load(f)

    # Create or get collection
    collection = client.get_or_create_collection(
        name="kanker_nl",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Check if already populated
    existing = collection.count()
    if existing > 0:
        print(f"  Collection already has {existing} chunks. Deleting and re-creating...")
        client.delete_collection("kanker_nl")
        collection = client.create_collection(
            name="kanker_nl",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    all_ids = []
    all_documents = []
    all_metadatas = []
    skipped = 0

    for url, page in pages.items():
        text = page.get("text", "")
        if not text.strip() or "Error 503" in text[:200]:
            skipped += 1
            continue

        # Normalize URL to match sitemap
        norm_url = url.strip().rstrip("/")
        if norm_url.startswith("https://kanker.nl/"):
            norm_url = norm_url.replace("https://kanker.nl/", "https://www.kanker.nl/", 1)

        meta = url_meta.get(norm_url)
        if meta is None:
            # Page was deduped out of the sitemap — skip
            skipped += 1
            continue

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            doc_id = f"kanker_nl_{hash(norm_url)}_{i}"
            all_ids.append(doc_id)
            all_documents.append(chunk)
            all_metadatas.append({
                "kankersoort": meta["kankersoort"],
                "section": meta["section"],
                "url": meta["url"],
                "title": meta["title"],
            })

    print(f"  Pages processed: {len(pages) - skipped}, skipped: {skipped}")
    print(f"  Total chunks: {len(all_documents)}")

    # ChromaDB has a batch limit of ~41666 — add in batches of 5000
    batch_size = 5000
    for i in range(0, len(all_documents), batch_size):
        end = min(i + batch_size, len(all_documents))
        collection.add(
            ids=all_ids[i:end],
            documents=all_documents[i:end],
            metadatas=all_metadatas[i:end],
        )
        print(f"  Added batch {i // batch_size + 1}: chunks {i}-{end}")

    print(f"  Done. Collection 'kanker_nl' has {collection.count()} chunks.")


def ingest_publications(client: chromadb.ClientAPI, ef):
    """Ingest PDF reports and scientific publications into the 'publications' collection."""
    print("\n=== Ingesting publications ===")

    collection = client.get_or_create_collection(
        name="publications",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    existing = collection.count()
    if existing > 0:
        print(f"  Collection already has {existing} chunks. Deleting and re-creating...")
        client.delete_collection("publications")
        collection = client.create_collection(
            name="publications",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    all_ids = []
    all_documents = []
    all_metadatas = []

    # Process both directories
    pdf_dirs = []
    if REPORTS_DIR.exists():
        pdf_dirs.append(REPORTS_DIR)
    if SCIENTIFIC_DIR.exists():
        pdf_dirs.append(SCIENTIFIC_DIR)

    for pdf_dir in pdf_dirs:
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            stem = pdf_path.stem
            meta = PUBLICATION_META.get(stem)
            if meta is None:
                print(f"  WARNING: No metadata for {pdf_path.name}, using defaults")
                meta = {
                    "source_type": "publication",
                    "title": stem.replace("_", " ").title(),
                    "language": "en",
                    "topic": "Unknown",
                }

            print(f"  Extracting: {pdf_path.name} ({meta['title']})")
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                print(f"    WARNING: No text extracted from {pdf_path.name}")
                continue

            chunks = chunk_text(text)
            print(f"    {len(chunks)} chunks from {len(text)} chars")

            for i, chunk in enumerate(chunks):
                doc_id = f"pub_{hash(stem)}_{i}"
                all_ids.append(doc_id)
                all_documents.append(chunk)
                all_metadatas.append({
                    "source_type": meta["source_type"],
                    "title": meta["title"],
                    "language": meta["language"],
                    "topic": meta["topic"],
                })

    print(f"  Total publication chunks: {len(all_documents)}")

    batch_size = 5000
    for i in range(0, len(all_documents), batch_size):
        end = min(i + batch_size, len(all_documents))
        collection.add(
            ids=all_ids[i:end],
            documents=all_documents[i:end],
            metadatas=all_metadatas[i:end],
        )
        print(f"  Added batch {i // batch_size + 1}: chunks {i}-{end}")

    print(f"  Done. Collection 'publications' has {collection.count()} chunks.")


def main():
    print(f"ChromaDB path: {CHROMADB_PATH}")
    print(f"Embedding model: {EMBEDDING_MODEL}")

    CHROMADB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    ef = get_embedding_function()

    ingest_kanker_nl(client, ef)
    ingest_publications(client, ef)

    # Summary
    print("\n=== Summary ===")
    for col_name in ["kanker_nl", "publications"]:
        try:
            col = client.get_collection(col_name, embedding_function=ef)
            print(f"  {col_name}: {col.count()} chunks")
        except Exception as e:
            print(f"  {col_name}: ERROR - {e}")


if __name__ == "__main__":
    main()
```

- [ ] **4.3** Test sitemap builder:

```bash
cd backend && uv run python -m ingestion.sitemap_builder
# Expected output:
#   Loading data/kanker_nl_pages_all.json ...
#   Loaded 2816 pages
#   Skipped 2 error/broken pages
#   Merged N duplicate URLs
#   Deduped N alias pages
#   Final sitemap: ~2600-2700 pages
#   Wrote data/sitemap.json
```

Verify:
```bash
python3 -c "import json; d=json.load(open('data/sitemap.json')); print(f'{len(d)} entries'); print(d[0])"
```

- [ ] **4.4** Test vectorize pipeline (this will download the embedding model on first run, ~1.5GB):

```bash
cd backend && uv run python -m ingestion.vectorize
# Expected output:
#   === Ingesting kanker.nl content ===
#   ...
#   Collection 'kanker_nl' has ~10000-15000 chunks
#   === Ingesting publications ===
#   ...
#   Collection 'publications' has ~1000-3000 chunks
```

Verify collections exist:
```bash
cd backend && uv run python -c "
import chromadb
client = chromadb.PersistentClient(path='../data/chromadb')
for name in ['kanker_nl', 'publications']:
    col = client.get_collection(name)
    print(f'{name}: {col.count()} chunks')
"
```

- [ ] **4.5** Commit: `git add backend/ingestion/sitemap_builder.py backend/ingestion/vectorize.py && git commit -m "feat(backend): kanker.nl sitemap builder and vector ingestion pipeline"`
