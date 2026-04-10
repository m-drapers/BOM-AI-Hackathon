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
from paths import resolve_repo_path

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
        from connectors.embeddings import get_embedding_function
        client = chromadb.PersistentClient(path=resolve_repo_path(chromadb_path))
        self._collection = client.get_collection(name=COLLECTION_NAME, embedding_function=get_embedding_function())
        logger.info(
            "KankerNLConnector initialised with collection '%s' (%d documents)",
            COLLECTION_NAME,
            self._collection.count(),
        )

    async def query(self, **params) -> SourceResult:
        """Dispatch to search_kanker_nl with the provided parameters."""
        return await search_kanker_nl(
            self,
            query=params.get("query", ""),
            kankersoort=params.get("kankersoort"),
            section=params.get("section"),
            n_results=params.get("n_results", DEFAULT_N_RESULTS),
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
