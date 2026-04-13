"""kanker.nl vector search connector.

Provides hybrid search (vector + BM25 keyword via RRF fusion) over
patient-facing cancer information pages from kanker.nl, stored in a
ChromaDB collection. Supports metadata filtering by kankersoort and section.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import chromadb

from connectors.base import Citation, SourceConnector, SourceResult
from paths import resolve_repo_path

logger = logging.getLogger(__name__)

COLLECTION_NAME = "kanker_nl"
DEFAULT_N_RESULTS = 5

# RRF weights: 85% vector, 15% BM25F (grid-searched optimal: k=40, 85/15)
RRF_VECTOR_WEIGHT = float(os.environ.get("RRF_VECTOR_WEIGHT", "0.85"))
RRF_BM25_WEIGHT = float(os.environ.get("RRF_BM25_WEIGHT", "0.15"))
# Set to "0" to disable RRF and use vector-only search
RRF_ENABLED = os.environ.get("RRF_ENABLED", "1") != "0"


class KankerNLConnector(SourceConnector):
    """Hybrid search connector for kanker.nl patient information.

    Uses Reciprocal Rank Fusion (RRF) to combine vector similarity search
    with BM25 keyword matching for improved recall (+4%) while maintaining
    strong MRR. Falls back to vector-only search if RRF is disabled or
    BM25 index fails to build.
    """

    name = "kanker_nl"
    description = (
        "Search the kanker.nl patient information database for general information "
        "about cancer types, diagnosis, treatment options, side effects, and life "
        "after diagnosis. Content is in Dutch. Optionally filter by cancer type "
        "(kankersoort) and section."
    )

    def __init__(self, chromadb_path: str = "data/chromadb") -> None:
        from connectors.embeddings import get_embedding_function
        self._chromadb_path = resolve_repo_path(chromadb_path)
        self._embedding_function = get_embedding_function()
        self._client = chromadb.PersistentClient(path=self._chromadb_path)
        self._collection = None
        self._hybrid_searcher = None
        self._resolve_collection()

    def _resolve_collection(self) -> None:
        """(Re)bind the collection handle. Tolerates the collection being
        missing or rebuilt while the backend is running."""
        try:
            self._collection = self._client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=self._embedding_function,
            )
            logger.info(
                "KankerNLConnector bound to '%s' (%d documents)",
                COLLECTION_NAME,
                self._collection.count(),
            )
            # Build BM25 index for hybrid search
            if RRF_ENABLED and self._hybrid_searcher is None:
                self._init_hybrid_search()
        except Exception as exc:
            self._collection = None
            logger.warning(
                "KankerNLConnector could not bind to '%s': %s",
                COLLECTION_NAME,
                exc,
            )

    def _init_hybrid_search(self) -> None:
        """Initialize the RRF hybrid searcher with BM25 index."""
        try:
            from connectors.rrf import HybridSearcher
            self._hybrid_searcher = HybridSearcher(
                self._collection,
                vector_weight=RRF_VECTOR_WEIGHT,
                bm25_weight=RRF_BM25_WEIGHT,
            )
            self._hybrid_searcher.build_bm25_index()
            logger.info(
                "RRF hybrid search enabled (vector=%.1f, bm25=%.1f)",
                RRF_VECTOR_WEIGHT, RRF_BM25_WEIGHT,
            )
        except Exception as exc:
            self._hybrid_searcher = None
            logger.warning("RRF hybrid search disabled: %s", exc)

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
        # Re-bind lazily if the collection wasn't available at startup
        # (e.g. ingestion hadn't run yet, or is rebuilding right now).
        if connector._collection is None:
            connector._resolve_collection()
        if connector._collection is None:
            return SourceResult(
                data=[],
                summary="De kanker.nl database is op dit moment niet beschikbaar.",
                sources=[],
                visualizable=False,
            )

        # Build metadata filter
        where_clause = _build_where_clause(kankersoort, section, connector)

        # Try RRF hybrid search first, fall back to vector-only
        if connector._hybrid_searcher is not None:
            try:
                hybrid_results = connector._hybrid_searcher.search(
                    query, n_results=n_results, where=where_clause,
                )
                documents = [r.text for r in hybrid_results]
                metadatas = [r.metadata for r in hybrid_results]
            except Exception as hybrid_exc:
                logger.warning("RRF search failed, falling back to vector: %s", hybrid_exc)
                documents, metadatas = _vector_search(connector, query, n_results, where_clause)
        else:
            documents, metadatas = _vector_search(connector, query, n_results, where_clause)

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


def _vector_search(connector, query, n_results, where_clause):
    """Pure vector search fallback."""
    query_kwargs: dict = {
        "query_texts": [query],
        "n_results": n_results,
    }
    if where_clause is not None:
        query_kwargs["where"] = where_clause

    try:
        results = connector._collection.query(**query_kwargs)
    except Exception as inner_exc:
        logger.warning("kanker_nl query failed (%s), re-resolving", inner_exc)
        connector._resolve_collection()
        if connector._collection is None:
            return [], []
        results = connector._collection.query(**query_kwargs)

    documents = results["documents"][0] if results["documents"][0] else []
    metadatas = results["metadatas"][0] if results["metadatas"][0] else []
    return documents, metadatas


# Known kankersoort slugs from the sitemap — used for exact-match filtering.
# Populated lazily from the ChromaDB collection at first use.
_KNOWN_SLUGS: set[str] = set()


def _normalize_kankersoort(raw: str) -> str:
    """Normalize a cancer type string to match sitemap slugs."""
    return raw.lower().strip().replace(" ", "-")


def _resolve_kankersoort_slug(raw: str, connector: "KankerNLConnector") -> str | None:
    """Find the best matching kankersoort slug from the known set.

    Returns the exact slug if found, or checks for prefix/substring matches.
    Returns None if no match (let semantic search handle relevance instead).
    """
    global _KNOWN_SLUGS
    if not _KNOWN_SLUGS and connector._collection is not None:
        try:
            # Get unique kankersoort values from the collection
            sample = connector._collection.get(limit=1, include=["metadatas"])
            if sample and sample["metadatas"]:
                # Fetch a larger sample to build the slug set
                all_meta = connector._collection.get(
                    limit=connector._collection.count(),
                    include=["metadatas"],
                )
                _KNOWN_SLUGS = {
                    m.get("kankersoort", "")
                    for m in all_meta["metadatas"]
                    if m.get("kankersoort")
                }
        except Exception:
            pass

    slug = _normalize_kankersoort(raw)

    # Exact match
    if slug in _KNOWN_SLUGS:
        return slug

    # Prefix/substring match (e.g. "darmkanker" matches "darmkanker-dikkedarmkanker")
    matches = [s for s in _KNOWN_SLUGS if slug in s or s in slug]
    if len(matches) == 1:
        return matches[0]

    # Multiple or no matches — skip filter, let semantic search handle it
    return None


def _build_where_clause(
    kankersoort: Optional[str],
    section: Optional[str],
    connector: Optional["KankerNLConnector"] = None,
) -> dict | None:
    """Build a ChromaDB where clause from optional filters.

    Returns None if no filters are provided or if no exact slug match is found
    (in which case semantic search handles relevance via the query text).
    """
    filters: list[dict] = []

    if kankersoort and connector is not None:
        slug = _resolve_kankersoort_slug(kankersoort, connector)
        if slug:
            filters.append({"kankersoort": {"$eq": slug}})
    if section:
        filters.append({"section": {"$eq": section}})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}
