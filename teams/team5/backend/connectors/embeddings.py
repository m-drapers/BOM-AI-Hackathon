"""Shared cached embedding function for ChromaDB connectors."""

import logging
import os

logger = logging.getLogger(__name__)

_cached_ef = None


def get_embedding_function():
    """Return a cached SentenceTransformer embedding function for ChromaDB."""
    global _cached_ef
    if _cached_ef is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        model_name = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
        logger.info("Loading embedding model: %s (one-time)", model_name)
        _cached_ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
    return _cached_ef
