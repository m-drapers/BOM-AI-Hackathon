# Cancer Information Chat — Implementation Plan (Part 2: Connectors)

> Continues from Part 1. See `2026-04-10-cancer-chat-impl-plan-part1.md` for project setup and ingestion.

---

## Task 5: kanker.nl Vector Search Connector

**Goal:** Build a connector that searches the `kanker_nl` ChromaDB collection with optional metadata filters for `kankersoort` and `section`.

**Files:**

| Action | Path |
|--------|------|
| Create | `backend/connectors/kanker_nl.py` |
| Create | `backend/tests/test_connectors/__init__.py` |
| Create | `backend/tests/test_connectors/test_kanker_nl.py` |

### Step 5.1: Write the failing test

- [ ] Create `backend/tests/test_connectors/__init__.py` (empty file)
- [ ] Create `backend/tests/test_connectors/test_kanker_nl.py`

```python
# backend/tests/test_connectors/test_kanker_nl.py
"""Tests for the kanker.nl vector search connector."""
import pytest
from unittest.mock import MagicMock, patch

from connectors.base import SourceResult, Citation
from connectors.kanker_nl import KankerNLConnector, search_kanker_nl


@pytest.fixture
def mock_collection():
    """Create a mock ChromaDB collection."""
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["chunk-001", "chunk-002"]],
        "documents": [
            [
                "Borstkanker is de meest voorkomende kankersoort bij vrouwen.",
                "De behandeling van borstkanker hangt af van het stadium.",
            ]
        ],
        "metadatas": [
            [
                {
                    "kankersoort": "borstkanker",
                    "section": "algemeen",
                    "url": "https://www.kanker.nl/kankersoorten/borstkanker/algemeen/borstkanker",
                    "title": "Borstkanker",
                },
                {
                    "kankersoort": "borstkanker",
                    "section": "behandelingen",
                    "url": "https://www.kanker.nl/kankersoorten/borstkanker/behandelingen/behandeling-borstkanker",
                    "title": "Behandeling borstkanker",
                },
            ]
        ],
        "distances": [[0.25, 0.42]],
    }
    return collection


@pytest.fixture
def mock_empty_collection():
    """Create a mock ChromaDB collection that returns no results."""
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    return collection


@pytest.fixture
def connector(mock_collection):
    """Create a KankerNLConnector with a mocked collection."""
    with patch("connectors.kanker_nl.chromadb") as mock_chromadb:
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        conn = KankerNLConnector(chromadb_path="data/chromadb")
    # Replace the collection with our mock directly
    conn._collection = mock_collection
    return conn


class TestKankerNLConnectorBasicQuery:
    """Test basic (unfiltered) queries."""

    @pytest.mark.asyncio
    async def test_basic_query_returns_source_result(self, connector, mock_collection):
        result = await search_kanker_nl(
            connector, query="Wat is borstkanker?"
        )

        assert isinstance(result, SourceResult)
        assert len(result.data) == 2
        assert "borstkanker" in result.data[0].lower()
        assert result.visualizable is False

    @pytest.mark.asyncio
    async def test_basic_query_includes_citations(self, connector, mock_collection):
        result = await search_kanker_nl(
            connector, query="Wat is borstkanker?"
        )

        assert len(result.sources) == 2
        assert all(isinstance(c, Citation) for c in result.sources)
        assert result.sources[0].url == "https://www.kanker.nl/kankersoorten/borstkanker/algemeen/borstkanker"
        assert result.sources[0].title == "Borstkanker"
        assert result.sources[0].reliability == "official"

    @pytest.mark.asyncio
    async def test_basic_query_calls_chromadb_without_where(self, connector, mock_collection):
        await search_kanker_nl(connector, query="Wat is kanker?")

        mock_collection.query.assert_called_once_with(
            query_texts=["Wat is kanker?"],
            n_results=5,
        )

    @pytest.mark.asyncio
    async def test_summary_is_populated(self, connector, mock_collection):
        result = await search_kanker_nl(
            connector, query="Wat is borstkanker?"
        )

        assert len(result.summary) > 0
        assert "2" in result.summary  # mentions number of results


class TestKankerNLConnectorFilteredQuery:
    """Test queries with kankersoort and/or section filters."""

    @pytest.mark.asyncio
    async def test_kankersoort_filter_applies_where_clause(self, connector, mock_collection):
        await search_kanker_nl(
            connector,
            query="behandeling",
            kankersoort="borstkanker",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"kankersoort": {"$eq": "borstkanker"}}

    @pytest.mark.asyncio
    async def test_section_filter_applies_where_clause(self, connector, mock_collection):
        await search_kanker_nl(
            connector,
            query="operatie",
            section="behandelingen",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"section": {"$eq": "behandelingen"}}

    @pytest.mark.asyncio
    async def test_combined_filters_apply_and_clause(self, connector, mock_collection):
        await search_kanker_nl(
            connector,
            query="chemo",
            kankersoort="longkanker",
            section="behandelingen",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {
            "$and": [
                {"kankersoort": {"$eq": "longkanker"}},
                {"section": {"$eq": "behandelingen"}},
            ]
        }


class TestKankerNLConnectorEmptyResults:
    """Test handling of empty results."""

    @pytest.mark.asyncio
    async def test_empty_results_return_appropriate_summary(self, mock_empty_collection):
        with patch("connectors.kanker_nl.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = mock_empty_collection
            mock_chromadb.PersistentClient.return_value = mock_client
            conn = KankerNLConnector(chromadb_path="data/chromadb")
        conn._collection = mock_empty_collection

        result = await search_kanker_nl(conn, query="iets heel specifieks")

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "geen" in result.summary.lower() or "no " in result.summary.lower()
        assert result.sources == []


class TestKankerNLConnectorErrorHandling:
    """Test error handling when ChromaDB fails."""

    @pytest.mark.asyncio
    async def test_chromadb_exception_returns_error_result(self, connector, mock_collection):
        mock_collection.query.side_effect = Exception("ChromaDB connection lost")

        result = await search_kanker_nl(connector, query="test")

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "error" in result.summary.lower() or "fout" in result.summary.lower()
        assert result.sources == []
```

- [ ] Run test (expect failure):

```bash
cd backend && python -m pytest tests/test_connectors/test_kanker_nl.py -v
```

### Step 5.2: Implement the connector

- [ ] Create `backend/connectors/kanker_nl.py`

```python
# backend/connectors/kanker_nl.py
"""kanker.nl vector search connector.

Provides semantic search over patient-facing cancer information pages
from kanker.nl, stored in a ChromaDB collection. Supports metadata
filtering by kankersoort (cancer type) and section.
"""
from __future__ import annotations

import logging
from typing import Optional

import chromadb

from connectors.base import Citation, SourceConnector, SourceResult

logger = logging.getLogger(__name__)

COLLECTION_NAME = "kanker_nl"
DEFAULT_N_RESULTS = 5


class KankerNLConnector(SourceConnector):
    """Vector search connector for kanker.nl patient information."""

    name = "kanker_nl"
    description = (
        "Search the kanker.nl patient information database for general information "
        "about cancer types, diagnosis, treatment options, side effects, and life "
        "after diagnosis. Content is in Dutch. Optionally filter by cancer type "
        "(kankersoort) and section."
    )

    def __init__(self, chromadb_path: str = "data/chromadb") -> None:
        client = chromadb.PersistentClient(path=chromadb_path)
        self._collection = client.get_collection(name=COLLECTION_NAME)
        logger.info(
            "KankerNLConnector initialised with collection '%s' (%d documents)",
            COLLECTION_NAME,
            self._collection.count(),
        )


async def search_kanker_nl(
    connector: KankerNLConnector,
    query: str,
    kankersoort: Optional[str] = None,
    section: Optional[str] = None,
    n_results: int = DEFAULT_N_RESULTS,
) -> SourceResult:
    """Search kanker.nl content with optional metadata filters.

    Parameters
    ----------
    connector:
        An initialised KankerNLConnector instance.
    query:
        Free-text search query.
    kankersoort:
        Optional cancer type slug to filter on (e.g. "borstkanker").
    section:
        Optional section filter (e.g. "behandelingen", "diagnose").
    n_results:
        Maximum number of chunks to return.

    Returns
    -------
    SourceResult
        Contains matched text passages, a human-readable summary,
        and citations with kanker.nl URLs.
    """
    try:
        # Build query kwargs
        query_kwargs: dict = {
            "query_texts": [query],
            "n_results": n_results,
        }

        # Apply metadata filters
        where_clause = _build_where_clause(kankersoort, section)
        if where_clause is not None:
            query_kwargs["where"] = where_clause

        results = connector._collection.query(**query_kwargs)

        # Extract documents and metadata from ChromaDB response
        documents = results["documents"][0] if results["documents"][0] else []
        metadatas = results["metadatas"][0] if results["metadatas"][0] else []

        if not documents:
            return SourceResult(
                data=[],
                summary="Geen resultaten gevonden op kanker.nl voor deze zoekopdracht.",
                sources=[],
                visualizable=False,
            )

        # Deduplicate citations by URL
        seen_urls: set[str] = set()
        citations: list[Citation] = []
        for meta in metadatas:
            url = meta.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                citations.append(
                    Citation(
                        url=url,
                        title=meta.get("title", "kanker.nl"),
                        reliability="official",
                    )
                )

        summary = (
            f"Gevonden: {len(documents)} relevante passage(s) op kanker.nl"
        )
        if kankersoort:
            summary += f" over {kankersoort}"
        if section:
            summary += f" in sectie '{section}'"
        summary += "."

        return SourceResult(
            data=documents,
            summary=summary,
            sources=citations,
            visualizable=False,
        )

    except Exception as exc:
        logger.exception("Error querying kanker.nl collection: %s", exc)
        return SourceResult(
            data=[],
            summary=f"Er is een fout opgetreden bij het doorzoeken van kanker.nl: {exc}",
            sources=[],
            visualizable=False,
        )


def _build_where_clause(
    kankersoort: Optional[str],
    section: Optional[str],
) -> dict | None:
    """Build a ChromaDB where clause from optional filters.

    Returns None if no filters are provided.
    """
    filters: list[dict] = []

    if kankersoort:
        filters.append({"kankersoort": {"$eq": kankersoort}})
    if section:
        filters.append({"section": {"$eq": section}})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}
```

- [ ] Run tests (expect pass):

```bash
cd backend && python -m pytest tests/test_connectors/test_kanker_nl.py -v
```

- [ ] Verify all 9 tests pass, then commit:

```bash
git add backend/connectors/kanker_nl.py \
       backend/tests/test_connectors/__init__.py \
       backend/tests/test_connectors/test_kanker_nl.py
git commit -m "feat: add kanker.nl vector search connector with filter support"
```

---

## Task 6: NKR-Cijfers API Connector

**Goal:** Build an async connector that queries the Netherlands Cancer Registry API for incidence, survival, and stage distribution data. Handles the tricky body format divergence between `/filter-groups` and `/data` endpoints.

**Files:**

| Action | Path |
|--------|------|
| Create | `backend/connectors/nkr_cijfers.py` |
| Create | `backend/tests/test_connectors/test_nkr_cijfers.py` |

### Step 6.1: Write the failing test

- [ ] Create `backend/tests/test_connectors/test_nkr_cijfers.py`

```python
# backend/tests/test_connectors/test_nkr_cijfers.py
"""Tests for the NKR-Cijfers API connector."""
import pytest
import httpx
import json
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.base import SourceResult, Citation, ChartData
from connectors.nkr_cijfers import (
    NKRCijfersConnector,
    get_cancer_incidence,
    get_survival_rates,
    get_stage_distribution,
)


# ---------------------------------------------------------------------------
# Fixtures: fake API responses
# ---------------------------------------------------------------------------

FAKE_NAVIGATION_ITEMS = [
    {
        "id": 1,
        "code": "C50",
        "name": "Borstkanker",
        "children": [],
    },
    {
        "id": 2,
        "code": "C34",
        "name": "Longkanker",
        "children": [],
    },
    {
        "id": 3,
        "code": "C18-C20",
        "name": "Dikkedarmkanker",
        "children": [],
    },
]

FAKE_CONFIGURATION = {
    "pages": [
        {"id": 1, "slug": "incidence", "name": "Incidentie"},
        {"id": 2, "slug": "stage-distribution", "name": "Stadiuminformatie"},
        {"id": 3, "slug": "survival", "name": "Overleving"},
    ]
}

FAKE_FILTER_GROUPS = {
    "filterGroups": [
        {
            "name": "Geslacht",
            "filters": [
                {"id": "sex-1", "name": "Man", "value": "1"},
                {"id": "sex-2", "name": "Vrouw", "value": "2"},
                {"id": "sex-3", "name": "Totaal", "value": "3"},
            ],
        },
        {
            "name": "Periode",
            "filters": [
                {"id": "period-2020", "name": "2020", "value": "2020"},
                {"id": "period-2021", "name": "2021", "value": "2021"},
            ],
        },
    ]
}

FAKE_INCIDENCE_DATA = {
    "data": [
        {
            "label": "2020",
            "values": [
                {"name": "Aantal", "value": 14948},
                {"name": "ESR", "value": 130.2},
            ],
        },
        {
            "label": "2021",
            "values": [
                {"name": "Aantal", "value": 15123},
                {"name": "ESR", "value": 131.5},
            ],
        },
    ]
}

FAKE_SURVIVAL_DATA = {
    "data": [
        {
            "label": "1-jaars",
            "values": [
                {"name": "Overleving", "value": 95.2},
            ],
        },
        {
            "label": "5-jaars",
            "values": [
                {"name": "Overleving", "value": 87.4},
            ],
        },
    ]
}

FAKE_STAGE_DATA = {
    "data": [
        {
            "label": "Stadium I",
            "values": [
                {"name": "Percentage", "value": 42.1},
            ],
        },
        {
            "label": "Stadium II",
            "values": [
                {"name": "Percentage", "value": 28.3},
            ],
        },
        {
            "label": "Stadium III",
            "values": [
                {"name": "Percentage", "value": 18.7},
            ],
        },
        {
            "label": "Stadium IV",
            "values": [
                {"name": "Percentage", "value": 10.9},
            ],
        },
    ]
}


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient that returns fake API responses."""
    client = AsyncMock(spec=httpx.AsyncClient)

    async def mock_post(url: str, **kwargs):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()

        if url.endswith("/navigation-items"):
            response.json.return_value = FAKE_NAVIGATION_ITEMS
        elif url.endswith("/configuration"):
            response.json.return_value = FAKE_CONFIGURATION
        elif url.endswith("/filter-groups"):
            response.json.return_value = FAKE_FILTER_GROUPS
        elif url.endswith("/data"):
            # Determine which data to return based on the request body
            body = kwargs.get("json", {})
            page_slug = body.get("navigation", {}).get("pageSlug", "")
            if page_slug == "survival":
                response.json.return_value = FAKE_SURVIVAL_DATA
            elif page_slug == "stage-distribution":
                response.json.return_value = FAKE_STAGE_DATA
            else:
                response.json.return_value = FAKE_INCIDENCE_DATA
        else:
            response.json.return_value = {}

        return response

    client.post = mock_post
    return client


@pytest.fixture
async def connector(mock_httpx_client):
    """Create a NKRCijfersConnector with mocked HTTP client."""
    with patch("connectors.nkr_cijfers.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        conn = NKRCijfersConnector()
        conn._client = mock_httpx_client
        await conn.initialize()
        return conn


class TestNavigationCaching:
    """Test that navigation items are cached at init."""

    @pytest.mark.asyncio
    async def test_navigation_items_are_cached(self, connector):
        conn = await connector
        assert len(conn._navigation_items) == 3
        assert conn._navigation_items[0]["name"] == "Borstkanker"

    @pytest.mark.asyncio
    async def test_cancer_type_name_resolves_to_code(self, connector):
        conn = await connector
        code = conn._resolve_cancer_type("Borstkanker")
        assert code == "C50"

    @pytest.mark.asyncio
    async def test_cancer_type_name_case_insensitive(self, connector):
        conn = await connector
        code = conn._resolve_cancer_type("borstkanker")
        assert code == "C50"

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_none(self, connector):
        conn = await connector
        code = conn._resolve_cancer_type("onbekende kanker")
        assert code is None


class TestIncidenceQuery:
    """Test get_cancer_incidence builds correct request and parses response."""

    @pytest.mark.asyncio
    async def test_incidence_returns_source_result(self, connector):
        conn = await connector
        result = await get_cancer_incidence(
            conn,
            cancer_type="Borstkanker",
            period="2020",
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True
        assert len(result.data) > 0

    @pytest.mark.asyncio
    async def test_incidence_request_uses_navigation_key(self, connector):
        """CRITICAL: /data endpoint must use 'navigation' key, NOT 'currentNavigation'."""
        conn = await connector
        # Wrap the mock post to capture the body
        original_post = conn._client.post
        captured_bodies = []

        async def capturing_post(url, **kwargs):
            captured_bodies.append({"url": url, "json": kwargs.get("json")})
            return await original_post(url, **kwargs)

        conn._client.post = capturing_post
        await get_cancer_incidence(conn, cancer_type="Borstkanker", period="2020")

        # Find the /data call
        data_calls = [c for c in captured_bodies if c["url"].endswith("/data")]
        assert len(data_calls) >= 1
        body = data_calls[0]["json"]
        assert "navigation" in body, "The /data endpoint must use 'navigation' key"
        assert "currentNavigation" not in body, "The /data endpoint must NOT use 'currentNavigation'"

    @pytest.mark.asyncio
    async def test_incidence_includes_citations(self, connector):
        conn = await connector
        result = await get_cancer_incidence(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert len(result.sources) >= 1
        assert result.sources[0].reliability == "official"
        assert "nkr-cijfers" in result.sources[0].url or "iknl" in result.sources[0].url

    @pytest.mark.asyncio
    async def test_incidence_summary_mentions_cancer_type(self, connector):
        conn = await connector
        result = await get_cancer_incidence(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert "Borstkanker" in result.summary or "borstkanker" in result.summary.lower()


class TestSurvivalQuery:
    """Test get_survival_rates."""

    @pytest.mark.asyncio
    async def test_survival_returns_source_result(self, connector):
        conn = await connector
        result = await get_survival_rates(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_survival_data_contains_rates(self, connector):
        conn = await connector
        result = await get_survival_rates(
            conn, cancer_type="Borstkanker", period="2020"
        )

        # Data should contain survival percentages
        assert len(result.data) > 0


class TestStageDistribution:
    """Test get_stage_distribution."""

    @pytest.mark.asyncio
    async def test_stage_returns_source_result(self, connector):
        conn = await connector
        result = await get_stage_distribution(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_stage_data_contains_stages(self, connector):
        conn = await connector
        result = await get_stage_distribution(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert len(result.data) > 0


class TestErrorHandling:
    """Test error handling for API failures."""

    @pytest.mark.asyncio
    async def test_api_failure_returns_error_result(self, connector):
        conn = await connector

        async def failing_post(url, **kwargs):
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

        conn._client.post = failing_post

        result = await get_cancer_incidence(
            conn, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "error" in result.summary.lower() or "fout" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_error(self, connector):
        conn = await connector
        result = await get_cancer_incidence(
            conn, cancer_type="niet bestaande kanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert "niet gevonden" in result.summary.lower() or "not found" in result.summary.lower()
```

- [ ] Run test (expect failure):

```bash
cd backend && python -m pytest tests/test_connectors/test_nkr_cijfers.py -v
```

### Step 6.2: Implement the connector

- [ ] Create `backend/connectors/nkr_cijfers.py`

```python
# backend/connectors/nkr_cijfers.py
"""NKR-Cijfers API connector.

Provides access to Netherlands Cancer Registry statistics: incidence,
prevalence, mortality, survival, stage distribution, and conditional
survival. This is the authoritative source for epidemiological data.

CRITICAL IMPLEMENTATION DETAIL:
The /data endpoint uses the key "navigation" in the JSON body.
The /filter-groups endpoint uses the key "currentNavigation".
Mixing these up produces silent 200 responses with empty data arrays.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from connectors.base import ChartData, Citation, SourceConnector, SourceResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nkr-cijfers.iknl.nl/api"

# Page slugs as defined in the NKR-Cijfers configuration
PAGE_INCIDENCE = "incidence"
PAGE_SURVIVAL = "survival"
PAGE_STAGE = "stage-distribution"
PAGE_PREVALENCE = "prevalence"
PAGE_MORTALITY = "mortality"
PAGE_CONDITIONAL_SURVIVAL = "conditional-survival"


class NKRCijfersConnector(SourceConnector):
    """Async connector for the NKR-Cijfers API.

    Caches navigation items at init for fast cancer type resolution.
    Implements three tools: incidence, survival, and stage distribution.
    """

    name = "nkr_cijfers"
    description = (
        "Query the Netherlands Cancer Registry for incidence (new cases), "
        "survival rates, and stage distribution data. Returns counts, rates, "
        "and percentages for requested cancer types and periods. Data is "
        "authoritative and covers 1961 to present."
    )

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._navigation_items: list[dict[str, Any]] = []
        self._configuration: dict[str, Any] = {}
        self._name_to_code: dict[str, str] = {}

    async def initialize(self) -> None:
        """Cache navigation items and configuration from the API.

        Must be called once at application startup before any queries.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        # Cache navigation items (cancer type hierarchy)
        response = await self._client.post(f"{BASE_URL}/navigation-items", json={})
        response.raise_for_status()
        self._navigation_items = response.json()

        # Build name -> code lookup (case-insensitive)
        self._name_to_code = {}
        self._index_navigation(self._navigation_items)

        # Cache configuration (available pages)
        response = await self._client.post(f"{BASE_URL}/configuration", json={})
        response.raise_for_status()
        self._configuration = response.json()

        logger.info(
            "NKRCijfersConnector initialised: %d cancer types cached",
            len(self._name_to_code),
        )

    def _index_navigation(self, items: list[dict[str, Any]]) -> None:
        """Recursively index navigation items for name -> code lookup."""
        for item in items:
            name = item.get("name", "")
            code = item.get("code", "")
            if name and code:
                self._name_to_code[name.lower()] = code
            children = item.get("children", [])
            if children:
                self._index_navigation(children)

    def _resolve_cancer_type(self, cancer_type: str) -> str | None:
        """Resolve a human-readable cancer type name to its NKR code.

        Parameters
        ----------
        cancer_type:
            Human-readable name (e.g. "Borstkanker"). Case-insensitive.

        Returns
        -------
        str or None
            The NKR code (e.g. "C50") or None if not found.
        """
        return self._name_to_code.get(cancer_type.lower())

    def _find_navigation_item(self, code: str) -> dict[str, Any] | None:
        """Find the full navigation item dict by code."""
        return self._search_items(self._navigation_items, code)

    def _search_items(
        self, items: list[dict[str, Any]], code: str
    ) -> dict[str, Any] | None:
        for item in items:
            if item.get("code") == code:
                return item
            found = self._search_items(item.get("children", []), code)
            if found:
                return found
        return None

    # ------------------------------------------------------------------
    # Request body builders
    # ------------------------------------------------------------------

    def _build_data_body(
        self,
        page_slug: str,
        navigation_item: dict[str, Any],
        period: str | None = None,
        sex: str | None = None,
        age_group: str | None = None,
        region: str | None = None,
        group_by: str = "period",
    ) -> dict[str, Any]:
        """Build the JSON body for the /data endpoint.

        CRITICAL: This endpoint uses the key "navigation", NOT "currentNavigation".
        Using "currentNavigation" will produce a silent 200 with empty data.
        """
        body: dict[str, Any] = {
            "navigation": {
                "id": navigation_item["id"],
                "code": navigation_item["code"],
                "name": navigation_item["name"],
                "pageSlug": page_slug,
            },
            "groupBy": group_by,
            "aggregateBy": [],
        }

        # Add filters
        filters: list[dict[str, Any]] = []
        if period:
            filters.append({"name": "Periode", "value": period})
        if sex:
            sex_map = {"male": "1", "man": "1", "female": "2", "vrouw": "2", "both": "3", "totaal": "3"}
            sex_value = sex_map.get(sex.lower(), "3")
            filters.append({"name": "Geslacht", "value": sex_value})
        if age_group:
            filters.append({"name": "Leeftijdsgroep", "value": age_group})
        if region:
            filters.append({"name": "Regio", "value": region})

        if filters:
            body["filters"] = filters

        return body

    def _build_filter_groups_body(
        self,
        page_slug: str,
        navigation_item: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the JSON body for the /filter-groups endpoint.

        CRITICAL: This endpoint uses the key "currentNavigation", NOT "navigation".
        """
        return {
            "currentNavigation": {
                "id": navigation_item["id"],
                "code": navigation_item["code"],
                "name": navigation_item["name"],
                "pageSlug": page_slug,
            },
        }

    # ------------------------------------------------------------------
    # Internal data fetching
    # ------------------------------------------------------------------

    async def _fetch_data(
        self,
        page_slug: str,
        cancer_type: str,
        period: str,
        sex: str | None = None,
        age_group: str | None = None,
        region: str | None = None,
        group_by: str = "period",
    ) -> SourceResult:
        """Fetch data from the /data endpoint for a given page and cancer type.

        This is the shared implementation for all three tool methods.
        """
        try:
            # Resolve cancer type name to code
            code = self._resolve_cancer_type(cancer_type)
            if code is None:
                return SourceResult(
                    data=[],
                    summary=(
                        f"Kankersoort '{cancer_type}' niet gevonden in het NKR. "
                        "Controleer de spelling of probeer een andere naam."
                    ),
                    sources=[],
                    visualizable=False,
                )

            nav_item = self._find_navigation_item(code)
            if nav_item is None:
                return SourceResult(
                    data=[],
                    summary=f"Navigatie-item voor code '{code}' niet gevonden.",
                    sources=[],
                    visualizable=False,
                )

            # Build the request body (using "navigation" key for /data)
            body = self._build_data_body(
                page_slug=page_slug,
                navigation_item=nav_item,
                period=period,
                sex=sex,
                age_group=age_group,
                region=region,
                group_by=group_by,
            )

            response = await self._client.post(f"{BASE_URL}/data", json=body)
            response.raise_for_status()
            raw = response.json()

            data_rows = raw.get("data", [])
            if not data_rows:
                return SourceResult(
                    data=[],
                    summary=(
                        f"Geen data beschikbaar voor {cancer_type} "
                        f"({page_slug}, periode {period})."
                    ),
                    sources=[
                        Citation(
                            url=f"https://nkr-cijfers.iknl.nl/{page_slug}",
                            title=f"NKR-Cijfers: {page_slug}",
                            reliability="official",
                        )
                    ],
                    visualizable=False,
                )

            # Parse into structured data
            parsed_data = []
            for row in data_rows:
                entry = {"label": row.get("label", "")}
                for val in row.get("values", []):
                    entry[val["name"]] = val["value"]
                parsed_data.append(entry)

            # Generate chart data
            chart = self._make_chart_data(page_slug, cancer_type, parsed_data)

            # Build summary
            summary = self._make_summary(page_slug, cancer_type, period, parsed_data)

            return SourceResult(
                data=parsed_data,
                summary=summary,
                sources=[
                    Citation(
                        url=f"https://nkr-cijfers.iknl.nl/{page_slug}",
                        title=f"NKR-Cijfers: {cancer_type} - {page_slug}",
                        reliability="official",
                    )
                ],
                visualizable=True,
                chart_data=chart,
            )

        except Exception as exc:
            logger.exception("Error fetching NKR data: %s", exc)
            return SourceResult(
                data=[],
                summary=f"Er is een fout opgetreden bij het ophalen van NKR data: {exc}",
                sources=[],
                visualizable=False,
            )

    # ------------------------------------------------------------------
    # Chart and summary helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_chart_data(
        page_slug: str,
        cancer_type: str,
        parsed_data: list[dict[str, Any]],
    ) -> ChartData | None:
        """Generate chart data from parsed API response."""
        if not parsed_data:
            return None

        # Determine chart type and keys based on page
        value_keys = [k for k in parsed_data[0] if k != "label"]
        if not value_keys:
            return None

        y_key = value_keys[0]

        if page_slug == PAGE_STAGE:
            return ChartData(
                chart_type="bar",
                title=f"Stadiumverdeling {cancer_type}",
                data=parsed_data,
                x_key="label",
                y_key=y_key,
            )
        elif page_slug == PAGE_SURVIVAL:
            return ChartData(
                chart_type="bar",
                title=f"Overleving {cancer_type}",
                data=parsed_data,
                x_key="label",
                y_key=y_key,
            )
        else:
            # Incidence, prevalence, mortality -> line chart over time
            return ChartData(
                chart_type="line",
                title=f"Incidentie {cancer_type}",
                data=parsed_data,
                x_key="label",
                y_key=y_key,
            )

    @staticmethod
    def _make_summary(
        page_slug: str,
        cancer_type: str,
        period: str,
        parsed_data: list[dict[str, Any]],
    ) -> str:
        """Generate a human-readable summary of the data."""
        n = len(parsed_data)

        if page_slug == PAGE_INCIDENCE:
            if n > 0 and "Aantal" in parsed_data[-1]:
                latest = parsed_data[-1]
                return (
                    f"Incidentie {cancer_type}: {n} datapunt(en) gevonden. "
                    f"Meest recente ({latest['label']}): "
                    f"{latest['Aantal']} nieuwe gevallen."
                )
            return f"Incidentie {cancer_type}: {n} datapunt(en) gevonden voor periode {period}."

        if page_slug == PAGE_SURVIVAL:
            if n > 0 and "Overleving" in parsed_data[0]:
                rates = ", ".join(
                    f"{d['label']}: {d['Overleving']}%" for d in parsed_data
                )
                return f"Overleving {cancer_type}: {rates}."
            return f"Overlevingsdata {cancer_type}: {n} datapunt(en) gevonden."

        if page_slug == PAGE_STAGE:
            if n > 0 and "Percentage" in parsed_data[0]:
                stages = ", ".join(
                    f"{d['label']}: {d['Percentage']}%" for d in parsed_data
                )
                return f"Stadiumverdeling {cancer_type}: {stages}."
            return f"Stadiumverdeling {cancer_type}: {n} datapunt(en) gevonden."

        return f"NKR data voor {cancer_type}: {n} datapunt(en) gevonden."

    # ------------------------------------------------------------------
    # Public tool methods
    # ------------------------------------------------------------------


async def get_cancer_incidence(
    connector: NKRCijfersConnector,
    cancer_type: str,
    period: str,
    sex: str | None = None,
    age_group: str | None = None,
    region: str | None = None,
) -> SourceResult:
    """Query the NKR for incidence (new cases) data.

    Parameters
    ----------
    connector:
        An initialised NKRCijfersConnector.
    cancer_type:
        Cancer type name (e.g. "Borstkanker"). Resolved to NKR code internally.
    period:
        Year or range (e.g. "2020" or "2015-2020").
    sex:
        Optional: "male", "female", or "both".
    age_group:
        Optional: e.g. "60-74".
    region:
        Optional: Dutch province name or "national".

    Returns
    -------
    SourceResult
        With visualizable=True and structured data for charts.
    """
    return await connector._fetch_data(
        page_slug=PAGE_INCIDENCE,
        cancer_type=cancer_type,
        period=period,
        sex=sex,
        age_group=age_group,
        region=region,
        group_by="period",
    )


async def get_survival_rates(
    connector: NKRCijfersConnector,
    cancer_type: str,
    period: str,
    sex: str | None = None,
    age_group: str | None = None,
) -> SourceResult:
    """Query the NKR for survival rates from diagnosis.

    Returns 1-year, 5-year, and 10-year relative survival percentages.
    """
    return await connector._fetch_data(
        page_slug=PAGE_SURVIVAL,
        cancer_type=cancer_type,
        period=period,
        sex=sex,
        age_group=age_group,
        group_by="period",
    )


async def get_stage_distribution(
    connector: NKRCijfersConnector,
    cancer_type: str,
    period: str,
    sex: str | None = None,
) -> SourceResult:
    """Query the NKR for stage distribution data.

    Returns percentage breakdown across TNM stages (I, II, III, IV).
    """
    return await connector._fetch_data(
        page_slug=PAGE_STAGE,
        cancer_type=cancer_type,
        period=period,
        sex=sex,
        group_by="stage",
    )
```

- [ ] Run tests (expect pass):

```bash
cd backend && python -m pytest tests/test_connectors/test_nkr_cijfers.py -v
```

- [ ] Verify all tests pass, then commit:

```bash
git add backend/connectors/nkr_cijfers.py \
       backend/tests/test_connectors/test_nkr_cijfers.py
git commit -m "feat: add NKR-Cijfers API connector with incidence, survival, stage tools"
```

### Step 6.3: Verify the critical body format divergence

This is the single most important correctness property in the entire connector. If you get this wrong, the API returns 200 OK with empty data and you will waste hours debugging.

- [ ] Manual verification checklist:

```bash
# Grep for "currentNavigation" -- must appear ONLY in _build_filter_groups_body
cd backend && grep -n "currentNavigation" connectors/nkr_cijfers.py

# Grep for "navigation" in _build_data_body -- must NOT be "currentNavigation"
cd backend && grep -n '"navigation"' connectors/nkr_cijfers.py
```

Expected: `currentNavigation` appears once (in the filter-groups builder). The string `"navigation"` appears in the data builder as the top-level key.

---

## Task 7: Cancer Atlas API Connector

**Goal:** Build a connector for the IKNL Cancer Atlas that returns Standardized Incidence Ratios (SIRs) at postcode level for 25 cancer groups. Uses GET endpoints (not POST like NKR).

**Files:**

| Action | Path |
|--------|------|
| Create | `backend/connectors/cancer_atlas.py` |
| Create | `backend/tests/test_connectors/test_cancer_atlas.py` |

### Step 7.1: Write the failing test

- [ ] Create `backend/tests/test_connectors/test_cancer_atlas.py`

```python
# backend/tests/test_connectors/test_cancer_atlas.py
"""Tests for the Cancer Atlas API connector."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.base import SourceResult, Citation
from connectors.cancer_atlas import (
    CancerAtlasConnector,
    get_regional_cancer_data,
    CANCER_GROUP_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures: fake API responses
# ---------------------------------------------------------------------------

FAKE_CANCER_GROUPS = [
    {"id": 1, "name": "Alle kanker", "validsex": 3},
    {"id": 2, "name": "Longkanker", "validsex": 3},
    {"id": 3, "name": "Borstkanker", "validsex": 2},
    {"id": 4, "name": "Prostaatkanker", "validsex": 1},
]

FAKE_PC3_DATA = [
    {
        "pc3": "560",
        "p10": 0.85,
        "p25": 0.92,
        "p50": 1.02,
        "p75": 1.12,
        "p90": 1.22,
        "credibility": 0.87,
    },
    {
        "pc3": "561",
        "p10": 1.10,
        "p25": 1.18,
        "p50": 1.30,
        "p75": 1.42,
        "p90": 1.55,
        "credibility": 0.92,
    },
    {
        "pc3": "100",
        "p10": 0.65,
        "p25": 0.72,
        "p50": 0.78,
        "p75": 0.85,
        "p90": 0.92,
        "credibility": 0.95,
    },
]


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient for Cancer Atlas API."""
    client = AsyncMock(spec=httpx.AsyncClient)

    async def mock_get(url: str, **kwargs):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()

        if "cancer-groups" in url or "kankergroepen" in url:
            response.json.return_value = FAKE_CANCER_GROUPS
        elif "/data/" in url or "/sir" in url:
            response.json.return_value = FAKE_PC3_DATA
        else:
            response.json.return_value = []

        return response

    client.get = mock_get
    return client


@pytest.fixture
async def connector(mock_httpx_client):
    """Create a CancerAtlasConnector with mocked HTTP client."""
    conn = CancerAtlasConnector()
    conn._client = mock_httpx_client
    await conn.initialize()
    return conn


class TestCancerGroupMapping:
    """Test the cancer group name -> ID mapping."""

    def test_mapping_contains_all_25_groups(self):
        assert len(CANCER_GROUP_MAP) == 25

    def test_mapping_contains_common_types(self):
        assert "Alle kanker" in CANCER_GROUP_MAP
        assert "Longkanker" in CANCER_GROUP_MAP
        assert "Borstkanker" in CANCER_GROUP_MAP
        assert "Prostaatkanker" in CANCER_GROUP_MAP
        assert "Dikkedarmkanker" in CANCER_GROUP_MAP

    def test_mapping_values_are_integers(self):
        for name, group_id in CANCER_GROUP_MAP.items():
            assert isinstance(group_id, int), f"ID for '{name}' should be int, got {type(group_id)}"


class TestCancerGroupCaching:
    """Test that cancer group definitions are cached at init."""

    @pytest.mark.asyncio
    async def test_groups_are_cached(self, connector):
        conn = await connector
        # The connector should have a cached list of groups
        assert conn._cancer_groups is not None
        assert len(conn._cancer_groups) > 0

    @pytest.mark.asyncio
    async def test_resolve_group_id(self, connector):
        conn = await connector
        group_id = conn._resolve_group_id("Longkanker")
        assert isinstance(group_id, int)

    @pytest.mark.asyncio
    async def test_resolve_group_id_case_insensitive(self, connector):
        conn = await connector
        group_id = conn._resolve_group_id("longkanker")
        assert isinstance(group_id, int)


class TestRegionalDataWithPostcode:
    """Test get_regional_cancer_data when a specific postcode is given."""

    @pytest.mark.asyncio
    async def test_postcode_query_returns_source_result(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker", postcode="560"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_postcode_query_returns_sir_data(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker", postcode="560"
        )

        assert len(result.data) > 0
        # Should contain SIR metrics
        area_data = result.data[0] if isinstance(result.data, list) else result.data
        assert "p50" in area_data or "sir" in str(area_data).lower()

    @pytest.mark.asyncio
    async def test_postcode_query_includes_citation(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker", postcode="560"
        )

        assert len(result.sources) >= 1
        assert isinstance(result.sources[0], Citation)
        assert "kankeratlas" in result.sources[0].url


class TestRegionalDataWithoutPostcode:
    """Test get_regional_cancer_data without a postcode (national summary)."""

    @pytest.mark.asyncio
    async def test_national_summary_returns_source_result(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_national_summary_returns_multiple_areas(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker"
        )

        # Without postcode, data should contain summary of multiple areas
        assert len(result.data) > 0


class TestSexFilter:
    """Test the sex/validsex filtering."""

    @pytest.mark.asyncio
    async def test_sex_parameter_is_passed(self, connector):
        conn = await connector
        # Borstkanker has validsex=2 (women only) - should still work when
        # requesting sex="female"
        result = await get_regional_cancer_data(
            conn, cancer_type="Borstkanker", sex="female"
        )

        assert isinstance(result, SourceResult)


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_error(self, connector):
        conn = await connector
        result = await get_regional_cancer_data(
            conn, cancer_type="Onbekende kankersoort"
        )

        assert isinstance(result, SourceResult)
        assert result.data == [] or result.data is None
        assert "niet gevonden" in result.summary.lower() or "not found" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_api_failure_returns_error_result(self, connector):
        conn = await connector

        async def failing_get(url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        conn._client.get = failing_get

        result = await get_regional_cancer_data(
            conn, cancer_type="Longkanker"
        )

        assert isinstance(result, SourceResult)
        assert result.data == [] or result.data is None
        assert "fout" in result.summary.lower() or "error" in result.summary.lower()
```

- [ ] Run test (expect failure):

```bash
cd backend && python -m pytest tests/test_connectors/test_cancer_atlas.py -v
```

### Step 7.2: Implement the connector

- [ ] Create `backend/connectors/cancer_atlas.py`

```python
# backend/connectors/cancer_atlas.py
"""Cancer Atlas API connector.

Provides geographic variation data for cancer incidence across the
Netherlands at postcode level. Returns Standardized Incidence Ratios
(SIRs) with Bayesian posterior distribution percentiles and credibility
scores.

Uses GET endpoints (not POST like NKR-Cijfers).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from connectors.base import ChartData, Citation, SourceConnector, SourceResult

logger = logging.getLogger(__name__)

# Base URLs
ATLAS_BASE_URL = "https://kankeratlas.iknl.nl/api"
STRAPI_BASE_URL = "https://iknl-atlas-strapi-prod.azurewebsites.net/api"

# Complete mapping of Dutch cancer group names to numeric IDs.
# Source: IKNL Cancer Atlas API /cancer-groups endpoint.
CANCER_GROUP_MAP: dict[str, int] = {
    "Alle kanker": 1,
    "Longkanker": 2,
    "Borstkanker": 3,
    "Prostaatkanker": 4,
    "Dikkedarmkanker": 5,
    "Huidkanker (melanoom)": 6,
    "Non-Hodgkin lymfoom": 7,
    "Blaaskanker": 8,
    "Nierkanker": 9,
    "Alvleesklierkanker": 10,
    "Maagkanker": 11,
    "Eierstokkanker": 12,
    "Baarmoederkanker": 13,
    "Leukemie": 14,
    "Slokdarmkanker": 15,
    "Leverkanker": 16,
    "Hersenkanker": 17,
    "Schildklierkanker": 18,
    "Hodgkin lymfoom": 19,
    "Keelkanker (larynx)": 20,
    "Mondholtekanker": 21,
    "Galweg- en galblaaskanker": 22,
    "Dunne darm kanker": 23,
    "Mesothelioom": 24,
    "Testiskanker": 25,
}

# validsex mapping: which sexes are valid for which cancer groups
# 1 = men only, 2 = women only, 3 = both sexes
VALIDSEX_MAP: dict[int, int] = {
    1: 3,   # Alle kanker
    2: 3,   # Longkanker
    3: 2,   # Borstkanker (women only)
    4: 1,   # Prostaatkanker (men only)
    5: 3,   # Dikkedarmkanker
    6: 3,   # Huidkanker (melanoom)
    7: 3,   # Non-Hodgkin lymfoom
    8: 3,   # Blaaskanker
    9: 3,   # Nierkanker
    10: 3,  # Alvleesklierkanker
    11: 3,  # Maagkanker
    12: 2,  # Eierstokkanker (women only)
    13: 2,  # Baarmoederkanker (women only)
    14: 3,  # Leukemie
    15: 3,  # Slokdarmkanker
    16: 3,  # Leverkanker
    17: 3,  # Hersenkanker
    18: 3,  # Schildklierkanker
    19: 3,  # Hodgkin lymfoom
    20: 3,  # Keelkanker (larynx)
    21: 3,  # Mondholtekanker
    22: 3,  # Galweg- en galblaaskanker
    23: 3,  # Dunne darm kanker
    24: 3,  # Mesothelioom
    25: 1,  # Testiskanker (men only)
}

SEX_NAME_TO_CODE: dict[str, int] = {
    "male": 1,
    "man": 1,
    "men": 1,
    "female": 2,
    "vrouw": 2,
    "women": 2,
    "both": 3,
    "totaal": 3,
    "alle": 3,
}


class CancerAtlasConnector(SourceConnector):
    """Async connector for the IKNL Cancer Atlas.

    Caches cancer group definitions at init. Returns SIR data
    at PC3 (3-digit postcode) resolution.
    """

    name = "cancer_atlas"
    description = (
        "Look up regional cancer incidence data from the IKNL Cancer Atlas. "
        "Returns Standardized Incidence Ratios (SIRs) at postcode level for "
        "25 cancer groups, showing whether a region has higher or lower "
        "incidence than the national average. Can render as a map."
    )

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cancer_groups: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        """Cache cancer group definitions from the API.

        Must be called once at application startup.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        try:
            response = await self._client.get(f"{ATLAS_BASE_URL}/cancer-groups")
            response.raise_for_status()
            self._cancer_groups = response.json()
        except Exception:
            # Fall back to static mapping if API is unreachable
            logger.warning(
                "Could not fetch cancer groups from API, using static mapping"
            )
            self._cancer_groups = [
                {"id": gid, "name": name}
                for name, gid in CANCER_GROUP_MAP.items()
            ]

        logger.info(
            "CancerAtlasConnector initialised: %d cancer groups cached",
            len(self._cancer_groups),
        )

    def _resolve_group_id(self, cancer_type: str) -> int | None:
        """Resolve a human-readable cancer group name to its numeric ID.

        Uses the static CANCER_GROUP_MAP as the primary lookup (case-insensitive),
        falling back to the cached API groups.
        """
        # Try static map first (case-insensitive)
        for name, gid in CANCER_GROUP_MAP.items():
            if name.lower() == cancer_type.lower():
                return gid

        # Try cached API groups
        for group in self._cancer_groups:
            if group.get("name", "").lower() == cancer_type.lower():
                return group["id"]

        return None

    def _resolve_sex_code(self, sex: str | None) -> int | None:
        """Resolve sex string to numeric code (1=men, 2=women, 3=both)."""
        if sex is None:
            return None
        return SEX_NAME_TO_CODE.get(sex.lower())

    def _validate_sex_for_group(self, group_id: int, sex_code: int | None) -> int:
        """Ensure the requested sex is valid for the cancer group.

        If the group only supports one sex (e.g. Borstkanker = women only),
        override the request to match.
        """
        valid = VALIDSEX_MAP.get(group_id, 3)

        if valid == 3:
            # Both sexes valid; use requested or default to 3 (both)
            return sex_code if sex_code is not None else 3
        else:
            # Only one sex valid; override
            return valid


async def get_regional_cancer_data(
    connector: CancerAtlasConnector,
    cancer_type: str,
    sex: str | None = None,
    postcode: str | None = None,
) -> SourceResult:
    """Look up regional cancer data from the Cancer Atlas.

    Parameters
    ----------
    connector:
        An initialised CancerAtlasConnector.
    cancer_type:
        Cancer group name in Dutch (e.g. "Longkanker").
    sex:
        Optional: "male", "female", or "both".
    postcode:
        Optional: 3- or 4-digit postcode prefix. When provided, returns
        data for that specific area. When omitted, returns a national
        summary with top-5 highest and lowest areas.

    Returns
    -------
    SourceResult
        With visualizable=True and SIR data.
    """
    try:
        # Resolve cancer type to group ID
        group_id = connector._resolve_group_id(cancer_type)
        if group_id is None:
            return SourceResult(
                data=[],
                summary=(
                    f"Kankersoort '{cancer_type}' niet gevonden in de Kankeratlas. "
                    f"Beschikbare groepen: {', '.join(list(CANCER_GROUP_MAP.keys())[:10])}..."
                ),
                sources=[],
                visualizable=False,
            )

        # Resolve and validate sex parameter
        sex_code = connector._resolve_sex_code(sex)
        sex_code = connector._validate_sex_for_group(group_id, sex_code)

        # Build API URL for PC3-level data
        url = f"{ATLAS_BASE_URL}/data/{group_id}/pc3"
        params: dict[str, Any] = {"sex": sex_code}

        response = await connector._client.get(url, params=params)
        response.raise_for_status()
        all_areas: list[dict[str, Any]] = response.json()

        if not all_areas:
            return SourceResult(
                data=[],
                summary=f"Geen regionale data beschikbaar voor {cancer_type}.",
                sources=[
                    Citation(
                        url="https://kankeratlas.iknl.nl",
                        title="IKNL Kankeratlas",
                        reliability="official",
                    )
                ],
                visualizable=False,
            )

        citation = Citation(
            url=f"https://kankeratlas.iknl.nl/{cancer_type.lower().replace(' ', '-')}",
            title=f"Kankeratlas: {cancer_type}",
            reliability="official",
        )

        if postcode is not None:
            # Return data for a specific postcode area
            return _build_postcode_result(
                all_areas, postcode, cancer_type, citation
            )
        else:
            # Return national summary
            return _build_national_summary(
                all_areas, cancer_type, citation
            )

    except Exception as exc:
        logger.exception("Error fetching Cancer Atlas data: %s", exc)
        return SourceResult(
            data=[],
            summary=f"Er is een fout opgetreden bij het ophalen van Kankeratlas data: {exc}",
            sources=[],
            visualizable=False,
        )


def _build_postcode_result(
    all_areas: list[dict[str, Any]],
    postcode: str,
    cancer_type: str,
    citation: Citation,
) -> SourceResult:
    """Build SourceResult for a specific postcode area."""
    # Find matching area
    matches = [a for a in all_areas if str(a.get("pc3", "")) == str(postcode)]

    if not matches:
        return SourceResult(
            data=[],
            summary=(
                f"Geen data gevonden voor postcodegebied {postcode} "
                f"voor {cancer_type}."
            ),
            sources=[citation],
            visualizable=False,
        )

    area = matches[0]
    sir = area.get("p50", 1.0)

    if sir > 1.1:
        comparison = "hoger dan"
    elif sir < 0.9:
        comparison = "lager dan"
    else:
        comparison = "vergelijkbaar met"

    summary = (
        f"Postcodegebied {postcode} - {cancer_type}: "
        f"SIR = {sir:.2f} ({comparison} het landelijk gemiddelde). "
        f"Betrouwbaarheid: {area.get('credibility', 'onbekend')}. "
        f"Bereik (p10-p90): {area.get('p10', '?'):.2f} - {area.get('p90', '?'):.2f}."
    )

    return SourceResult(
        data=[area],
        summary=summary,
        sources=[citation],
        visualizable=True,
    )


def _build_national_summary(
    all_areas: list[dict[str, Any]],
    cancer_type: str,
    citation: Citation,
) -> SourceResult:
    """Build SourceResult with national summary (top/bottom 5 areas)."""
    # Sort by SIR (p50) to find highest and lowest areas
    sorted_areas = sorted(all_areas, key=lambda a: a.get("p50", 1.0))

    lowest_5 = sorted_areas[:5]
    highest_5 = sorted_areas[-5:]

    highest_desc = ", ".join(
        f"PC3 {a.get('pc3', '?')} (SIR={a.get('p50', 0):.2f})"
        for a in reversed(highest_5)
    )
    lowest_desc = ", ".join(
        f"PC3 {a.get('pc3', '?')} (SIR={a.get('p50', 0):.2f})"
        for a in lowest_5
    )

    summary = (
        f"Landelijk overzicht {cancer_type} ({len(all_areas)} postcodegebieden). "
        f"Hoogste SIR: {highest_desc}. "
        f"Laagste SIR: {lowest_desc}."
    )

    return SourceResult(
        data=all_areas,
        summary=summary,
        sources=[citation],
        visualizable=True,
    )
```

- [ ] Run tests (expect pass):

```bash
cd backend && python -m pytest tests/test_connectors/test_cancer_atlas.py -v
```

- [ ] Verify all tests pass, then commit:

```bash
git add backend/connectors/cancer_atlas.py \
       backend/tests/test_connectors/test_cancer_atlas.py
git commit -m "feat: add Cancer Atlas connector with SIR data and postcode lookup"
```

---

## Task 8: Publications Vector Search Connector

**Goal:** Build a connector that searches the `publications` ChromaDB collection for scientific papers and institutional reports, with optional filters for source type and language.

**Files:**

| Action | Path |
|--------|------|
| Create | `backend/connectors/publications.py` |
| Create | `backend/tests/test_connectors/test_publications.py` |

### Step 8.1: Write the failing test

- [ ] Create `backend/tests/test_connectors/test_publications.py`

```python
# backend/tests/test_connectors/test_publications.py
"""Tests for the publications vector search connector."""
import pytest
from unittest.mock import MagicMock, patch

from connectors.base import SourceResult, Citation
from connectors.publications import PublicationsConnector, search_publications


@pytest.fixture
def mock_collection():
    """Create a mock ChromaDB collection with publication results."""
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["pub-001", "pub-002", "pub-003"]],
        "documents": [
            [
                "Comorbidities significantly impact cancer survival across eight tumour types.",
                "Machine learning models can predict ovarian cancer outcomes with 0.82 AUC.",
                "Genderverschillen in kankerincidentie zijn het grootst bij longkanker.",
            ]
        ],
        "metadatas": [
            [
                {
                    "source_type": "publication",
                    "title": "Comorbidities and survival in 8 cancers",
                    "language": "en",
                    "topic": "comorbidities",
                },
                {
                    "source_type": "publication",
                    "title": "Ovarian cancer ML prediction",
                    "language": "en",
                    "topic": "ovarian cancer",
                },
                {
                    "source_type": "report",
                    "title": "Genderverschillen in kanker",
                    "language": "nl",
                    "topic": "gender differences",
                },
            ]
        ],
        "distances": [[0.18, 0.34, 0.45]],
    }
    return collection


@pytest.fixture
def mock_empty_collection():
    """Create a mock ChromaDB collection that returns no results."""
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    return collection


@pytest.fixture
def connector(mock_collection):
    """Create a PublicationsConnector with a mocked collection."""
    with patch("connectors.publications.chromadb") as mock_chromadb:
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_chromadb.PersistentClient.return_value = mock_client
        conn = PublicationsConnector(chromadb_path="data/chromadb")
    conn._collection = mock_collection
    return conn


class TestPublicationsBasicQuery:
    """Test basic (unfiltered) queries."""

    @pytest.mark.asyncio
    async def test_basic_query_returns_source_result(self, connector, mock_collection):
        result = await search_publications(
            connector, query="cancer survival comorbidities"
        )

        assert isinstance(result, SourceResult)
        assert len(result.data) == 3
        assert result.visualizable is False

    @pytest.mark.asyncio
    async def test_basic_query_includes_citations(self, connector, mock_collection):
        result = await search_publications(
            connector, query="cancer survival"
        )

        assert len(result.sources) == 3
        assert all(isinstance(c, Citation) for c in result.sources)
        assert result.sources[0].title == "Comorbidities and survival in 8 cancers"

    @pytest.mark.asyncio
    async def test_basic_query_calls_chromadb_without_where(self, connector, mock_collection):
        await search_publications(connector, query="cancer survival")

        mock_collection.query.assert_called_once_with(
            query_texts=["cancer survival"],
            n_results=5,
        )

    @pytest.mark.asyncio
    async def test_summary_is_populated(self, connector, mock_collection):
        result = await search_publications(
            connector, query="cancer survival"
        )

        assert len(result.summary) > 0
        assert "3" in result.summary


class TestPublicationsFilteredQuery:
    """Test queries with source_type and/or language filters."""

    @pytest.mark.asyncio
    async def test_source_type_filter(self, connector, mock_collection):
        await search_publications(
            connector,
            query="kankerincidentie",
            source_type="report",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"source_type": {"$eq": "report"}}

    @pytest.mark.asyncio
    async def test_language_filter(self, connector, mock_collection):
        await search_publications(
            connector,
            query="survival rates",
            language="en",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"language": {"$eq": "en"}}

    @pytest.mark.asyncio
    async def test_combined_filters(self, connector, mock_collection):
        await search_publications(
            connector,
            query="genderverschillen",
            source_type="report",
            language="nl",
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {
            "$and": [
                {"source_type": {"$eq": "report"}},
                {"language": {"$eq": "nl"}},
            ]
        }


class TestPublicationsEmptyResults:
    """Test handling of empty results."""

    @pytest.mark.asyncio
    async def test_empty_results_return_appropriate_summary(self, mock_empty_collection):
        with patch("connectors.publications.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_client.get_collection.return_value = mock_empty_collection
            mock_chromadb.PersistentClient.return_value = mock_client
            conn = PublicationsConnector(chromadb_path="data/chromadb")
        conn._collection = mock_empty_collection

        result = await search_publications(conn, query="iets heel specifieks")

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "geen" in result.summary.lower() or "no " in result.summary.lower()
        assert result.sources == []


class TestPublicationsErrorHandling:
    """Test error handling when ChromaDB fails."""

    @pytest.mark.asyncio
    async def test_chromadb_exception_returns_error_result(self, connector, mock_collection):
        mock_collection.query.side_effect = Exception("ChromaDB disk full")

        result = await search_publications(connector, query="test")

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "error" in result.summary.lower() or "fout" in result.summary.lower()
        assert result.sources == []
```

- [ ] Run test (expect failure):

```bash
cd backend && python -m pytest tests/test_connectors/test_publications.py -v
```

### Step 8.2: Implement the connector

- [ ] Create `backend/connectors/publications.py`

```python
# backend/connectors/publications.py
"""Publications vector search connector.

Provides semantic search over scientific publications and institutional
reports about cancer, stored in a ChromaDB collection. Supports filtering
by source type (report/publication) and language (nl/en).
"""
from __future__ import annotations

import logging
from typing import Optional

import chromadb

from connectors.base import Citation, SourceConnector, SourceResult

logger = logging.getLogger(__name__)

COLLECTION_NAME = "publications"
DEFAULT_N_RESULTS = 5

# Reliability mapping by source type
RELIABILITY_MAP = {
    "publication": "peer-reviewed",
    "report": "official",
}


class PublicationsConnector(SourceConnector):
    """Vector search connector for indexed publications and reports."""

    name = "publications"
    description = (
        "Search indexed scientific publications and institutional reports about "
        "cancer. Includes Lancet and ESMO papers (English) and IKNL reports on "
        "gender differences, metastatic cancer, and colorectal trends (Dutch). "
        "Filter by source type or language."
    )

    def __init__(self, chromadb_path: str = "data/chromadb") -> None:
        client = chromadb.PersistentClient(path=chromadb_path)
        self._collection = client.get_collection(name=COLLECTION_NAME)
        logger.info(
            "PublicationsConnector initialised with collection '%s' (%d documents)",
            COLLECTION_NAME,
            self._collection.count(),
        )


async def search_publications(
    connector: PublicationsConnector,
    query: str,
    source_type: str | None = None,
    language: str | None = None,
    n_results: int = DEFAULT_N_RESULTS,
) -> SourceResult:
    """Search publications and reports with optional metadata filters.

    Parameters
    ----------
    connector:
        An initialised PublicationsConnector instance.
    query:
        Free-text search query.
    source_type:
        Optional: "report" or "publication".
    language:
        Optional: "nl" or "en".
    n_results:
        Maximum number of chunks to return.

    Returns
    -------
    SourceResult
        Contains matched text passages, a human-readable summary,
        and citations to document titles.
    """
    try:
        # Build query kwargs
        query_kwargs: dict = {
            "query_texts": [query],
            "n_results": n_results,
        }

        # Apply metadata filters
        where_clause = _build_where_clause(source_type, language)
        if where_clause is not None:
            query_kwargs["where"] = where_clause

        results = connector._collection.query(**query_kwargs)

        # Extract documents and metadata
        documents = results["documents"][0] if results["documents"][0] else []
        metadatas = results["metadatas"][0] if results["metadatas"][0] else []

        if not documents:
            return SourceResult(
                data=[],
                summary="Geen resultaten gevonden in de publicatiedatabase voor deze zoekopdracht.",
                sources=[],
                visualizable=False,
            )

        # Build citations from document metadata
        citations: list[Citation] = []
        for meta in metadatas:
            title = meta.get("title", "Onbekend document")
            src_type = meta.get("source_type", "publication")
            reliability = RELIABILITY_MAP.get(src_type, "peer-reviewed")
            citations.append(
                Citation(
                    url=f"publications/{title.lower().replace(' ', '-')}",
                    title=title,
                    reliability=reliability,
                )
            )

        # Build summary
        source_counts: dict[str, int] = {}
        for meta in metadatas:
            st = meta.get("source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1

        type_desc = ", ".join(f"{count} {stype}(s)" for stype, count in source_counts.items())
        summary = f"Gevonden: {len(documents)} relevante passage(s) uit {type_desc}"
        if language:
            summary += f" (taal: {language})"
        summary += "."

        return SourceResult(
            data=documents,
            summary=summary,
            sources=citations,
            visualizable=False,
        )

    except Exception as exc:
        logger.exception("Error querying publications collection: %s", exc)
        return SourceResult(
            data=[],
            summary=f"Er is een fout opgetreden bij het doorzoeken van publicaties: {exc}",
            sources=[],
            visualizable=False,
        )


def _build_where_clause(
    source_type: str | None,
    language: str | None,
) -> dict | None:
    """Build a ChromaDB where clause from optional filters.

    Returns None if no filters are provided.
    """
    filters: list[dict] = []

    if source_type:
        filters.append({"source_type": {"$eq": source_type}})
    if language:
        filters.append({"language": {"$eq": language}})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}
```

- [ ] Run tests (expect pass):

```bash
cd backend && python -m pytest tests/test_connectors/test_publications.py -v
```

- [ ] Verify all tests pass, then commit:

```bash
git add backend/connectors/publications.py \
       backend/tests/test_connectors/test_publications.py
git commit -m "feat: add publications vector search connector with source_type/language filters"
```

---

## Pre-requisite: Base Connector Module

Tasks 5-8 depend on the `backend/connectors/base.py` module defining the shared types. If Part 1 has not been executed yet, create this file first:

- [ ] Create `backend/connectors/__init__.py` (empty)
- [ ] Create `backend/connectors/base.py`

```python
# backend/connectors/base.py
"""Base connector interface and shared data types.

All connectors share this common interface so that adding a new source
requires no changes to the orchestration layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class SourceConnector:
    """Abstract base for all source connectors.

    Subclasses must define `name` and `description` class attributes.
    Claude uses the description to decide when to invoke the connector.
    """

    name: str
    description: str


@dataclass
class Citation:
    """A citation to a specific source."""

    url: str
    title: str
    reliability: str  # e.g. "official", "peer-reviewed", "scraped"


@dataclass
class ChartData:
    """Structured chart data for the frontend."""

    chart_type: str  # "line", "bar", "value"
    title: str
    data: list[dict[str, Any]]
    x_key: str
    y_key: str


@dataclass
class SourceResult:
    """Result returned by every connector query.

    Even when data is empty (e.g. due to an error), the summary field
    is always populated so Claude can relay the information to the user
    instead of crashing.
    """

    data: Any  # structured data or text passages
    summary: str  # human-readable for Claude to narrate
    sources: list[Citation]  # URL + title + reliability
    visualizable: bool  # hint to frontend for chart/map rendering
    chart_data: Optional[ChartData] = None  # optional chart for frontend
```

- [ ] Create `backend/tests/__init__.py` (empty)

---

## Run All Connector Tests

After completing Tasks 5-8, run the full connector test suite:

```bash
cd backend && python -m pytest tests/test_connectors/ -v --tb=short
```

Expected: all tests pass across all four test files.

---

## Summary

| Task | Connector | Key Patterns | Files Created |
|------|-----------|-------------|---------------|
| 5 | kanker.nl Vector Search | ChromaDB query, metadata filters, `$and` clause | `kanker_nl.py`, `test_kanker_nl.py` |
| 6 | NKR-Cijfers API | `navigation` vs `currentNavigation`, name-to-code resolution, chart data | `nkr_cijfers.py`, `test_nkr_cijfers.py` |
| 7 | Cancer Atlas | GET endpoints, 25 cancer groups, SIR data, validsex handling, postcode lookup | `cancer_atlas.py`, `test_cancer_atlas.py` |
| 8 | Publications Vector Search | ChromaDB query, source_type/language filters, reliability mapping | `publications.py`, `test_publications.py` |

All connectors follow the same contract: return a `SourceResult` with data, summary, citations, and a visualizable flag. Error handling catches all exceptions and returns a `SourceResult` with a human-readable error summary instead of crashing.
