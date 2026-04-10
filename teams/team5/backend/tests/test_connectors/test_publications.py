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
