"""Tests for the NKR-Cijfers API connector."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.base import SourceResult, Citation
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
        assert len(connector._navigation_items) == 3
        assert connector._navigation_items[0]["name"] == "Borstkanker"

    @pytest.mark.asyncio
    async def test_cancer_type_name_resolves_to_code(self, connector):
        code = connector._resolve_cancer_type("Borstkanker")
        assert code == "C50"

    @pytest.mark.asyncio
    async def test_cancer_type_name_case_insensitive(self, connector):
        code = connector._resolve_cancer_type("borstkanker")
        assert code == "C50"

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_none(self, connector):
        code = connector._resolve_cancer_type("onbekende kanker")
        assert code is None


class TestIncidenceQuery:
    """Test get_cancer_incidence builds correct request and parses response."""

    @pytest.mark.asyncio
    async def test_incidence_returns_source_result(self, connector):
        result = await get_cancer_incidence(
            connector,
            cancer_type="Borstkanker",
            period="2020",
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True
        assert len(result.data) > 0

    @pytest.mark.asyncio
    async def test_incidence_request_uses_navigation_key(self, connector):
        """CRITICAL: /data endpoint must use 'navigation' key, NOT 'currentNavigation'."""
        # Wrap the mock post to capture the body
        original_post = connector._client.post
        captured_bodies = []

        async def capturing_post(url, **kwargs):
            captured_bodies.append({"url": url, "json": kwargs.get("json")})
            return await original_post(url, **kwargs)

        connector._client.post = capturing_post
        await get_cancer_incidence(connector, cancer_type="Borstkanker", period="2020")

        # Find the /data call
        data_calls = [c for c in captured_bodies if c["url"].endswith("/data")]
        assert len(data_calls) >= 1
        body = data_calls[0]["json"]
        assert "navigation" in body, "The /data endpoint must use 'navigation' key"
        assert "currentNavigation" not in body, "The /data endpoint must NOT use 'currentNavigation'"

    @pytest.mark.asyncio
    async def test_incidence_includes_citations(self, connector):
        result = await get_cancer_incidence(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert len(result.sources) >= 1
        assert result.sources[0].reliability == "official"
        assert "nkr-cijfers" in result.sources[0].url or "iknl" in result.sources[0].url

    @pytest.mark.asyncio
    async def test_incidence_summary_mentions_cancer_type(self, connector):
        result = await get_cancer_incidence(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert "Borstkanker" in result.summary or "borstkanker" in result.summary.lower()


class TestSurvivalQuery:
    """Test get_survival_rates."""

    @pytest.mark.asyncio
    async def test_survival_returns_source_result(self, connector):
        result = await get_survival_rates(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_survival_data_contains_rates(self, connector):
        result = await get_survival_rates(
            connector, cancer_type="Borstkanker", period="2020"
        )

        # Data should contain survival percentages
        assert len(result.data) > 0


class TestStageDistribution:
    """Test get_stage_distribution."""

    @pytest.mark.asyncio
    async def test_stage_returns_source_result(self, connector):
        result = await get_stage_distribution(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_stage_data_contains_stages(self, connector):
        result = await get_stage_distribution(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert len(result.data) > 0


class TestErrorHandling:
    """Test error handling for API failures."""

    @pytest.mark.asyncio
    async def test_api_failure_returns_error_result(self, connector):
        async def failing_post(url, **kwargs):
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

        connector._client.post = failing_post

        result = await get_cancer_incidence(
            connector, cancer_type="Borstkanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert result.data == []
        assert "error" in result.summary.lower() or "fout" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_error(self, connector):
        result = await get_cancer_incidence(
            connector, cancer_type="niet bestaande kanker", period="2020"
        )

        assert isinstance(result, SourceResult)
        assert "niet gevonden" in result.summary.lower() or "not found" in result.summary.lower()
