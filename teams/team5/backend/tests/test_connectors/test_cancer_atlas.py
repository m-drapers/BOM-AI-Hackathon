# backend/tests/test_connectors/test_cancer_atlas.py
"""Tests for the Cancer Atlas API connector."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.base import SourceResult, Citation
from connectors.cancer_atlas import (
    CancerAtlasConnector,
    get_regional_cancer_data,
    CANCER_GROUP_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures: fake API responses
# ---------------------------------------------------------------------------

FAKE_CANCER_GROUPS = [
    {"id": 1, "name": "Alle kanker", "validsex": 3},
    {"id": 2, "name": "Longkanker", "validsex": 3},
    {"id": 3, "name": "Borstkanker", "validsex": 2},
    {"id": 4, "name": "Prostaatkanker", "validsex": 1},
]

FAKE_PC3_DATA = [
    {
        "pc3": "560",
        "p10": 0.85,
        "p25": 0.92,
        "p50": 1.02,
        "p75": 1.12,
        "p90": 1.22,
        "credibility": 0.87,
    },
    {
        "pc3": "561",
        "p10": 1.10,
        "p25": 1.18,
        "p50": 1.30,
        "p75": 1.42,
        "p90": 1.55,
        "credibility": 0.92,
    },
    {
        "pc3": "100",
        "p10": 0.65,
        "p25": 0.72,
        "p50": 0.78,
        "p75": 0.85,
        "p90": 0.92,
        "credibility": 0.95,
    },
]


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient for Cancer Atlas API."""
    client = AsyncMock(spec=httpx.AsyncClient)

    async def mock_get(url: str, **kwargs):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()

        if "cancer-groups" in url or "kankergroepen" in url:
            response.json.return_value = FAKE_CANCER_GROUPS
        elif "/data/" in url or "/sir" in url:
            response.json.return_value = FAKE_PC3_DATA
        else:
            response.json.return_value = []

        return response

    client.get = mock_get
    return client


@pytest.fixture
async def connector(mock_httpx_client):
    """Create a CancerAtlasConnector with mocked HTTP client."""
    conn = CancerAtlasConnector()
    conn._client = mock_httpx_client
    await conn.initialize()
    return conn


class TestCancerGroupMapping:
    """Test the cancer group name -> ID mapping."""

    def test_mapping_contains_all_25_groups(self):
        assert len(CANCER_GROUP_MAP) == 25

    def test_mapping_contains_common_types(self):
        assert "Alle kanker" in CANCER_GROUP_MAP
        assert "Longkanker" in CANCER_GROUP_MAP
        assert "Borstkanker" in CANCER_GROUP_MAP
        assert "Prostaatkanker" in CANCER_GROUP_MAP
        assert "Dikkedarmkanker" in CANCER_GROUP_MAP

    def test_mapping_values_are_integers(self):
        for name, group_id in CANCER_GROUP_MAP.items():
            assert isinstance(group_id, int), f"ID for '{name}' should be int, got {type(group_id)}"


class TestCancerGroupCaching:
    """Test that cancer group definitions are cached at init."""

    @pytest.mark.asyncio
    async def test_groups_are_cached(self, connector):
        # The connector should have a cached list of groups
        assert connector._cancer_groups is not None
        assert len(connector._cancer_groups) > 0

    @pytest.mark.asyncio
    async def test_resolve_group_id(self, connector):
        group_id = connector._resolve_group_id("Longkanker")
        assert isinstance(group_id, int)

    @pytest.mark.asyncio
    async def test_resolve_group_id_case_insensitive(self, connector):
        group_id = connector._resolve_group_id("longkanker")
        assert isinstance(group_id, int)


class TestRegionalDataWithPostcode:
    """Test get_regional_cancer_data when a specific postcode is given."""

    @pytest.mark.asyncio
    async def test_postcode_query_returns_source_result(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker", postcode="560"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True

    @pytest.mark.asyncio
    async def test_postcode_query_returns_sir_data(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker", postcode="560"
        )

        assert len(result.data) > 0
        # Should contain SIR metrics
        area_data = result.data[0] if isinstance(result.data, list) else result.data
        assert "p50" in area_data or "sir" in str(area_data).lower()

    @pytest.mark.asyncio
    async def test_postcode_query_includes_citation(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker", postcode="560"
        )

        assert len(result.sources) >= 1
        assert isinstance(result.sources[0], Citation)
        assert "kankeratlas" in result.sources[0].url


class TestRegionalDataWithoutPostcode:
    """Test get_regional_cancer_data without a postcode (national summary)."""

    @pytest.mark.asyncio
    async def test_national_summary_returns_source_result(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker"
        )

        assert isinstance(result, SourceResult)
        assert result.visualizable is True
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_national_summary_returns_multiple_areas(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker"
        )

        # Without postcode, data should contain summary of multiple areas
        assert len(result.data) > 0


class TestSexFilter:
    """Test the sex/validsex filtering."""

    @pytest.mark.asyncio
    async def test_sex_parameter_is_passed(self, connector):
        # Borstkanker has validsex=2 (women only) - should still work when
        # requesting sex="female"
        result = await get_regional_cancer_data(
            connector, cancer_type="Borstkanker", sex="female"
        )

        assert isinstance(result, SourceResult)


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_unknown_cancer_type_returns_error(self, connector):
        result = await get_regional_cancer_data(
            connector, cancer_type="Onbekende kankersoort"
        )

        assert isinstance(result, SourceResult)
        assert result.data == [] or result.data is None
        assert "niet gevonden" in result.summary.lower() or "not found" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_api_failure_returns_error_result(self, connector):
        async def failing_get(url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        connector._client.get = failing_get

        result = await get_regional_cancer_data(
            connector, cancer_type="Longkanker"
        )

        assert isinstance(result, SourceResult)
        assert result.data == [] or result.data is None
        assert "fout" in result.summary.lower() or "error" in result.summary.lower()
