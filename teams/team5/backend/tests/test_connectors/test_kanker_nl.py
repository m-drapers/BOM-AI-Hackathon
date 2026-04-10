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
