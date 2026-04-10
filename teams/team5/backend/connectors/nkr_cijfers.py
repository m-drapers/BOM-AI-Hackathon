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
from typing import Any

import httpx

from connectors.base import Citation, SourceConnector, SourceResult

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
            sex_map = {
                "male": "1",
                "man": "1",
                "female": "2",
                "vrouw": "2",
                "both": "3",
                "totaal": "3",
            }
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
                entry: dict[str, Any] = {"label": row.get("label", "")}
                for val in row.get("values", []):
                    entry[val["name"]] = val["value"]
                parsed_data.append(entry)

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
    # Summary helper
    # ------------------------------------------------------------------

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
    # SourceConnector.query implementation
    # ------------------------------------------------------------------

    async def query(self, **params) -> SourceResult:
        """Generic query method required by SourceConnector base class.

        Delegates to the appropriate tool method based on the 'page' parameter.
        """
        page = params.pop("page", PAGE_INCIDENCE)
        cancer_type = params.pop("cancer_type", "")
        period = params.pop("period", "")

        return await self._fetch_data(
            page_slug=page,
            cancer_type=cancer_type,
            period=period,
            sex=params.get("sex"),
            age_group=params.get("age_group"),
            region=params.get("region"),
            group_by=params.get("group_by", "period"),
        )


# ------------------------------------------------------------------
# Public tool methods (module-level functions)
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
