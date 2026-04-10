"""Tests for the FastAPI application."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock, patch

from main import SSEEvent, app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator that yields predefined SSE events."""

    async def mock_stream(request):
        yield SSEEvent(
            event="source_card",
            data=json.dumps(
                {
                    "source": "kanker_nl",
                    "url": "https://www.kanker.nl/borstkanker",
                    "reliability": "patient-info",
                    "contributed": True,
                }
            ),
        )
        yield SSEEvent(
            event="token",
            data=json.dumps({"text": "Borstkanker is "}),
        )
        yield SSEEvent(
            event="token",
            data=json.dumps({"text": "de meest voorkomende kankersoort."}),
        )
        yield SSEEvent(
            event="done",
            data=json.dumps(
                {
                    "message_id": "msg-001",
                    "sources_tried": ["kanker_nl"],
                }
            ),
        )

    orch = MagicMock()
    orch.stream = mock_stream
    return orch


# ---------------------------------------------------------------------------
# Tests: Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_correct_shape(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "llm_provider" in data
        assert "chromadb_collections" in data
        assert "version" in data
        assert data["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_health_returns_version(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

        data = response.json()
        assert data["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Tests: Feedback endpoint
# ---------------------------------------------------------------------------


class TestFeedbackEndpoint:

    @pytest.mark.asyncio
    async def test_feedback_stores_and_returns_id(self, tmp_path):
        """POST /api/feedback should store feedback and return an ID."""
        with patch(
            "backend.main.FEEDBACK_DB_PATH",
            str(tmp_path / "test_feedback.db"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                payload = {
                    "session_id": "sess-001",
                    "message_id": "msg-001",
                    "rating": "positive",
                    "comment": "Zeer nuttig!",
                    "query": "Wat is borstkanker?",
                    "sources_tried": ["kanker_nl"],
                    "profile": "patient",
                }
                response = await client.post("/api/feedback", json=payload)

            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert len(data["id"]) > 0

    @pytest.mark.asyncio
    async def test_feedback_negative_rating(self, tmp_path):
        """Negative feedback should also be stored."""
        with patch(
            "backend.main.FEEDBACK_DB_PATH",
            str(tmp_path / "test_feedback.db"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                payload = {
                    "session_id": "sess-002",
                    "message_id": "msg-002",
                    "rating": "negative",
                    "comment": "Informatie over bijwerkingen miste.",
                    "query": "Wat zijn de behandelingen?",
                    "sources_tried": ["kanker_nl", "nkr_cijfers"],
                    "profile": "professional",
                }
                response = await client.post("/api/feedback", json=payload)

            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_feedback_export_returns_csv(self, tmp_path):
        """GET /api/feedback/export should return CSV data."""
        db_path = str(tmp_path / "test_feedback.db")
        with patch("backend.main.FEEDBACK_DB_PATH", db_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # First store some feedback
                payload = {
                    "session_id": "sess-001",
                    "message_id": "msg-001",
                    "rating": "positive",
                    "query": "Wat is borstkanker?",
                    "sources_tried": ["kanker_nl"],
                }
                await client.post("/api/feedback", json=payload)

                # Then export
                response = await client.get("/api/feedback/export")

            assert response.status_code == 200
            assert "text/csv" in response.headers.get("content-type", "")
            content = response.text
            # CSV should have a header row
            assert "session_id" in content
            assert "rating" in content
            # Should contain our data
            assert "sess-001" in content


# ---------------------------------------------------------------------------
# Tests: Chat stream endpoint
# ---------------------------------------------------------------------------


class TestChatStreamEndpoint:

    @pytest.mark.asyncio
    async def test_chat_stream_returns_sse_events(self, mock_orchestrator):
        """POST /api/chat/stream should return SSE events."""

        # Override the orchestrator dependency
        with patch(
            "backend.main._create_orchestrator",
            return_value=mock_orchestrator,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                payload = {
                    "message": "Wat is borstkanker?",
                    "session_id": "sess-001",
                    "profile": "patient",
                    "history": [],
                }
                response = await client.post(
                    "/api/chat/stream",
                    json=payload,
                    headers={"Accept": "text/event-stream"},
                )

            assert response.status_code == 200
            body = response.text

            # Should contain SSE event markers
            assert "event:" in body or "data:" in body

    @pytest.mark.asyncio
    async def test_chat_stream_requires_message(self):
        """Missing message field should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            payload = {
                "session_id": "sess-001",
                "profile": "patient",
            }
            response = await client.post("/api/chat/stream", json=payload)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_stream_requires_valid_profile(self):
        """Invalid profile should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            payload = {
                "message": "Test",
                "session_id": "sess-001",
                "profile": "invalid_profile",
                "history": [],
            }
            response = await client.post("/api/chat/stream", json=payload)

        assert response.status_code == 422
