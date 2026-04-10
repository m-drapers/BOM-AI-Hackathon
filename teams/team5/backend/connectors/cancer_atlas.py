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

from connectors.base import Citation, SourceConnector, SourceResult

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

    async def query(self, **params) -> SourceResult:
        """Query the Cancer Atlas API.

        Delegates to get_regional_cancer_data with the provided params.
        """
        return await get_regional_cancer_data(
            self,
            cancer_type=params.get("cancer_type", ""),
            sex=params.get("sex"),
            postcode=params.get("postcode"),
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
