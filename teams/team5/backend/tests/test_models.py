"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from models import ChatRequest, ChartData, FeedbackEntry, SourceResult, Citation
from models import GegevensModel, IntakeSummarizeRequest, IntakeSummarizeResponse, IntakeSearchRequest


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(
            message="What is breast cancer?",
            session_id="abc-123",
            profile="patient",
        )
        assert req.message == "What is breast cancer?"
        assert req.profile == "patient"
        assert req.history == []

    def test_invalid_profile_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(
                message="Hello",
                session_id="abc-123",
                profile="hacker",
            )


class TestSourceResult:
    def test_construction(self):
        result = SourceResult(
            data={"incidence": 12000},
            summary="Breast cancer incidence in 2023.",
            sources=[
                Citation(
                    url="https://nkr.nl/data",
                    title="NKR Data",
                    reliability="high",
                )
            ],
            visualizable=True,
        )
        assert result.visualizable is True
        assert len(result.sources) == 1
        assert result.sources[0].title == "NKR Data"

    def test_none_data(self):
        result = SourceResult(
            data=None,
            summary="No data found.",
            sources=[],
            visualizable=False,
        )
        assert result.data is None


class TestFeedbackEntry:
    def test_auto_timestamp(self):
        entry = FeedbackEntry(
            session_id="sess-1",
            message_id="msg-1",
            rating="positive",
            query="survival rates",
            sources_tried=["nkr", "kanker_nl"],
        )
        assert entry.timestamp is not None

    def test_explicit_timestamp_preserved(self):
        from datetime import datetime, timezone

        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        entry = FeedbackEntry(
            session_id="sess-1",
            message_id="msg-1",
            rating="negative",
            query="treatment options",
            sources_tried=["pubmed"],
            timestamp=ts,
        )
        assert entry.timestamp == ts


class TestChartData:
    def test_line_chart(self):
        chart = ChartData(
            type="line",
            title="Incidence over time",
            data=[{"year": 2020, "count": 100}, {"year": 2021, "count": 110}],
            x_key="year",
            y_key="count",
        )
        assert chart.type == "line"
        assert len(chart.data) == 2

    def test_bar_chart_with_unit(self):
        chart = ChartData(
            type="bar",
            title="Survival rate",
            data=[{"stage": "I", "rate": 0.95}],
            x_key="stage",
            y_key="rate",
            unit="%",
        )
        assert chart.unit == "%"

    def test_value_type(self):
        chart = ChartData(
            type="value",
            title="Total cases",
            data=[{"value": 5000}],
            x_key="label",
            y_key="value",
        )
        assert chart.type == "value"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            ChartData(
                type="pie",
                title="Invalid",
                data=[],
                x_key="x",
                y_key="y",
            )


class TestGegevensModel:
    def test_defaults(self):
        gm = GegevensModel()
        assert gm.ai_bekendheid is None
        assert gm.gebruiker_type is None
        assert gm.vraag_tekst is None
        assert gm.kankersoort is None
        assert gm.vraag_type is None
        assert gm.samenvatting is None
        assert gm.bevestigd is False

    def test_valid_ai_bekendheid(self):
        gm = GegevensModel(ai_bekendheid="niet_bekend")
        assert gm.ai_bekendheid == "niet_bekend"

    def test_invalid_ai_bekendheid_rejected(self):
        with pytest.raises(ValidationError):
            GegevensModel(ai_bekendheid="very_known")

    def test_valid_gebruiker_type(self):
        gm = GegevensModel(gebruiker_type="patient")
        assert gm.gebruiker_type == "patient"

    def test_invalid_gebruiker_type_rejected(self):
        with pytest.raises(ValidationError):
            GegevensModel(gebruiker_type="hacker")

    def test_full_model(self):
        gm = GegevensModel(
            ai_bekendheid="enigszins",
            gebruiker_type="zorgverlener",
            vraag_tekst="Hoe vaak komt longkanker voor?",
            kankersoort="longkanker",
            vraag_type="cijfers",
            samenvatting="U zoekt cijfers over longkanker.",
            bevestigd=True,
        )
        assert gm.bevestigd is True
        assert gm.kankersoort == "longkanker"


class TestIntakeSummarizeRequest:
    def test_valid(self):
        req = IntakeSummarizeRequest(
            gebruiker_type="patient",
            vraag_tekst="Wat is borstkanker?",
        )
        assert req.gebruiker_type == "patient"
        assert req.vraag_tekst == "Wat is borstkanker?"

    def test_invalid_gebruiker_type(self):
        with pytest.raises(ValidationError):
            IntakeSummarizeRequest(
                gebruiker_type="alien",
                vraag_tekst="test",
            )


class TestIntakeSummarizeResponse:
    def test_valid(self):
        resp = IntakeSummarizeResponse(
            samenvatting="U zoekt info over borstkanker.",
            kankersoort="borstkanker",
            vraag_type="patient_info",
        )
        assert resp.kankersoort == "borstkanker"

    def test_geen_kankersoort(self):
        resp = IntakeSummarizeResponse(
            samenvatting="U zoekt algemene info.",
            kankersoort="geen",
            vraag_type="breed",
        )
        assert resp.kankersoort == "geen"


class TestIntakeSearchRequest:
    def test_valid(self):
        req = IntakeSearchRequest(
            ai_bekendheid="erg_bekend",
            gebruiker_type="onderzoeker",
            vraag_tekst="Overleving darmkanker",
            kankersoort="darmkanker",
            vraag_type="cijfers",
            samenvatting="U zoekt overlevingscijfers voor darmkanker.",
        )
        assert req.gebruiker_type == "onderzoeker"

    def test_requires_gebruiker_type(self):
        with pytest.raises(ValidationError):
            IntakeSearchRequest(
                ai_bekendheid="enigszins",
                vraag_tekst="test",
                samenvatting="test",
            )
