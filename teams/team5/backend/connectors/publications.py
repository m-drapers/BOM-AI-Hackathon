"""Publications vector search connector.

Provides semantic search over scientific publications and institutional
reports about cancer, stored in a ChromaDB collection. Supports filtering
by source type (report/publication) and language (nl/en).
"""
from __future__ import annotations

import logging

import chromadb

from connectors.base import Citation, SourceConnector, SourceResult
from paths import resolve_repo_path

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
        from connectors.embeddings import get_embedding_function
        client = chromadb.PersistentClient(path=resolve_repo_path(chromadb_path))
        self._collection = client.get_collection(name=COLLECTION_NAME, embedding_function=get_embedding_function())
        logger.info(
            "PublicationsConnector initialised with collection '%s' (%d documents)",
            COLLECTION_NAME,
            self._collection.count(),
        )

    async def query(self, **params) -> SourceResult:
        """Dispatch to search_publications with the given params."""
        return await search_publications(self, **params)


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

        # Build citations from document metadata. URLs should be persisted at ingest time.
        citations: list[Citation] = []
        seen_titles: set[str] = set()
        for meta in metadatas:
            title = meta.get("title", "Onbekend document")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            src_type = meta.get("source_type", "publication")
            reliability = RELIABILITY_MAP.get(src_type, "peer-reviewed")
            url = meta.get("url", "https://iknl.nl/onderzoek/publicaties")
            citations.append(
                Citation(
                    url=url,
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
