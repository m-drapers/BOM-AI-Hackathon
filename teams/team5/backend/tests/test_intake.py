"""Tests for intake module — summarize and search logic."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from intake import summarize_question
from models import IntakeSummarizeResponse


class TestSummarizeQuestion:
    @pytest.mark.asyncio
    async def test_returns_summarize_response(self):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content=json.dumps({
                        "samenvatting": "U zoekt informatie over borstkanker.",
                        "kankersoort": "borstkanker",
                        "vraag_type": "patient_info",
                    })
                )
            )
        ]

        with patch("intake.litellm.acompletion", return_value=mock_response):
            result = await summarize_question(
                gebruiker_type="patient",
                vraag_tekst="Wat is borstkanker?",
                model="test-model",
            )

        assert isinstance(result, IntakeSummarizeResponse)
        assert result.samenvatting == "U zoekt informatie over borstkanker."
        assert result.kankersoort == "borstkanker"
        assert result.vraag_type == "patient_info"

    @pytest.mark.asyncio
    async def test_handles_geen_kankersoort(self):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content=json.dumps({
                        "samenvatting": "U zoekt algemene informatie over kanker.",
                        "kankersoort": "geen",
                        "vraag_type": "breed",
                    })
                )
            )
        ]

        with patch("intake.litellm.acompletion", return_value=mock_response):
            result = await summarize_question(
                gebruiker_type="publiek",
                vraag_tekst="Wat doet IKNL?",
                model="test-model",
            )

        assert result.kankersoort == "geen"
        assert result.vraag_type == "breed"

    @pytest.mark.asyncio
    async def test_llm_returns_non_json_falls_back(self):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(content="This is not JSON")
            )
        ]

        with patch("intake.litellm.acompletion", return_value=mock_response):
            result = await summarize_question(
                gebruiker_type="patient",
                vraag_tekst="Wat is borstkanker?",
                model="test-model",
            )

        assert isinstance(result, IntakeSummarizeResponse)
        assert result.vraag_type == "breed"


from intake import search_and_format, _select_connectors
from models import Citation, SourceResult


class TestSelectConnectors:
    def test_patient_with_patient_info(self):
        result = _select_connectors("patient", "patient_info")
        assert result[0] == "kanker_nl"

    def test_onderzoeker_with_onderzoek(self):
        result = _select_connectors("onderzoeker", "onderzoek")
        assert result[0] == "publications"

    def test_beleidsmaker_with_regionaal(self):
        result = _select_connectors("beleidsmaker", "regionaal")
        assert result[0] == "cancer_atlas"

    def test_patient_with_cijfers(self):
        result = _select_connectors("patient", "cijfers")
        assert "nkr_cijfers" in result


class TestSearchAndFormat:
    @pytest.mark.asyncio
    async def test_returns_sse_events(self):
        mock_connector = MagicMock()
        mock_connector.name = "kanker_nl"
        mock_connector.query = AsyncMock(
            return_value=SourceResult(
                data={"content": "Borstkanker is..."},
                summary="Informatie over borstkanker van kanker.nl",
                sources=[
                    Citation(
                        url="https://kanker.nl/borstkanker",
                        title="Borstkanker - kanker.nl",
                        reliability="official",
                    )
                ],
                visualizable=False,
            )
        )

        mock_llm_response = AsyncMock()
        mock_llm_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content="Hier zijn de bronnen over borstkanker:\n\n1. [Borstkanker - kanker.nl](https://kanker.nl/borstkanker)"
                )
            )
        ]

        connectors = {"kanker_nl": mock_connector}

        events = []
        with patch("intake.litellm.acompletion", return_value=mock_llm_response):
            async for event in search_and_format(
                ai_bekendheid="enigszins",
                gebruiker_type="patient",
                vraag_tekst="Wat is borstkanker?",
                samenvatting="U zoekt informatie over borstkanker.",
                vraag_type="patient_info",
                kankersoort="borstkanker",
                connectors=connectors,
                model="test-model",
            ):
                events.append(event)

        event_types = [e.event for e in events]
        assert "source_card" in event_types
        assert "token" in event_types
        assert "done" in event_types


from httpx import ASGITransport, AsyncClient


class TestIntakeEndpoints:
    @pytest.mark.asyncio
    async def test_summarize_endpoint(self):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content=json.dumps({
                        "samenvatting": "U zoekt informatie over borstkanker.",
                        "kankersoort": "borstkanker",
                        "vraag_type": "patient_info",
                    })
                )
            )
        ]

        with patch("intake.litellm.acompletion", return_value=mock_response):
            from main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/intake/summarize", json={
                    "gebruiker_type": "patient",
                    "vraag_tekst": "Wat is borstkanker?",
                })

        assert resp.status_code == 200
        data = resp.json()
        assert "samenvatting" in data
        assert "kankersoort" in data
        assert "vraag_type" in data

    @pytest.mark.asyncio
    async def test_summarize_invalid_type(self):
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/intake/summarize", json={
                "gebruiker_type": "alien",
                "vraag_tekst": "test",
            })

        assert resp.status_code == 422
