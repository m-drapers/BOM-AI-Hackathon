"""Base interface for all source connectors."""

from abc import ABC, abstractmethod

from models import Citation, SourceResult

__all__ = ["SourceConnector", "SourceResult", "Citation"]


class SourceConnector(ABC):
    """Abstract base class that every data-source connector must implement."""

    name: str
    description: str

    @abstractmethod
    async def query(self, **params) -> SourceResult:
        ...
