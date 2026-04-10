"""Tests for the chat orchestrator."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator import ChatOrchestrator, SSEEvent
from models import ChatRequest, ChatMessage, SourceResult, Citation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kanker_nl_connector():
    conn = AsyncMock()
    conn.name = "kanker_nl"
    conn.description = (
        "Search the kanker.nl patient information database for general "
        "information about cancer types, diagnosis, treatment options, "
        "side effects, and life after diagnosis."
    )
    conn.query = AsyncMock(return_value=SourceResult(
        data={"text": "Borstkanker is de meest voorkomende kanker bij vrouwen."},
        summary="Borstkanker is de meest voorkomende kanker bij vrouwen in Nederland.",
        sources=[Citation(
            url="https://www.kanker.nl/kankersoorten/borstkanker",
            title="Borstkanker - Kanker.nl",
            reliability="patient-info",
        )],
        visualizable=False,
    ))
    return conn


@pytest.fixture
def nkr_connector():
    conn = AsyncMock()
    conn.name = "nkr_cijfers"
    conn.description = (
        "Query the Netherlands Cancer Registry for incidence data."
    )
    conn.query = AsyncMock(return_value=SourceResult(
        data={"incidence": [{"year": 2020, "count": 15000}]},
        summary="In 2020 waren er 15.000 nieuwe gevallen van borstkanker.",
        sources=[Citation(
            url="https://nkr-cijfers.iknl.nl/",
            title="NKR-Cijfers Incidentie",
            reliability="official",
        )],
        visualizable=True,
    ))
    return conn


@pytest.fixture
def atlas_connector():
    conn = AsyncMock()
    conn.name = "cancer_atlas"
    conn.description = "Look up regional cancer incidence data from the IKNL Cancer Atlas."
    conn.query = AsyncMock(return_value=SourceResult(
        data={},
        summary="Geen data beschikbaar.",
        sources=[],
        visualizable=False,
    ))
    return conn


@pytest.fixture
def publications_connector():
    conn = AsyncMock()
    conn.name = "publications"
    conn.description = "Search indexed scientific publications and institutional reports."
    conn.query = AsyncMock(return_value=SourceResult(
        data={},
        summary="Geen relevante publicaties gevonden.",
        sources=[],
        visualizable=False,
    ))
    return conn


@pytest.fixture
def all_connectors(kanker_nl_connector, nkr_connector, atlas_connector, publications_connector):
    return [kanker_nl_connector, nkr_connector, atlas_connector, publications_connector]


@pytest.fixture
def patient_request():
    return ChatRequest(
        message="Wat is borstkanker?",
        session_id="test-session-001",
        profile="patient",
        history=[],
    )


@pytest.fixture
def professional_request():
    return ChatRequest(
        message="Wat zijn de overlevingscijfers voor stadium III colorectaal carcinoom?",
        session_id="test-session-002",
        profile="professional",
        history=[],
    )


@pytest.fixture
def policymaker_request():
    return ChatRequest(
        message="Hoe verschilt de incidentie van longkanker per regio?",
        session_id="test-session-003",
        profile="policymaker",
        history=[],
    )


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_use_id: str = "toolu_01"):
    """Create a mock LiteLLM response that requests a tool call."""
    tool_call = MagicMock()
    tool_call.id = tool_use_id
    tool_call.type = "function"
    tool_call.function = MagicMock()
    tool_call.function.name = tool_name
    tool_call.function.arguments = json.dumps(tool_input)

    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = None
    choice.message.tool_calls = [tool_call]
    choice.message.role = "assistant"
    choice.finish_reason = "tool_calls"

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_text_response(text: str):
    """Create a mock LiteLLM response with final text."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = text
    choice.message.tool_calls = None
    choice.message.role = "assistant"
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_streaming_chunks(text: str, chunk_size: int = 10):
    """Create mock streaming chunks for a text response."""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = text[i:i + chunk_size]
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = None if i + chunk_size < len(text) else "stop"
        chunk.choices = [choice]
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Tests: system prompt selection
# ---------------------------------------------------------------------------

class TestSystemPromptSelection:
    """Verify the correct system prompt is built per profile."""

    def test_patient_prompt_contains_warm_tone(self, all_connectors, patient_request):
        orch = ChatOrchestrator(connectors=all_connectors)
        prompt = orch._build_system_prompt(patient_request.profile)
        assert "warm" in prompt.lower() or "begrijpelijk" in prompt.lower() or "eenvoudig" in prompt.lower()
        assert "kanker.nl" in prompt
        assert "geen arts" in prompt.lower() or "informatieassistent" in prompt.lower()

    def test_professional_prompt_contains_clinical_tone(self, all_connectors, professional_request):
        orch = ChatOrchestrator(connectors=all_connectors)
        prompt = orch._build_system_prompt(professional_request.profile)
        assert "klinisch" in prompt.lower() or "precies" in prompt.lower() or "nauwkeurig" in prompt.lower()
        assert "NKR" in prompt or "nkr" in prompt.lower()

    def test_policymaker_prompt_contains_analytical_tone(self, all_connectors, policymaker_request):
        orch = ChatOrchestrator(connectors=all_connectors)
        prompt = orch._build_system_prompt(policymaker_request.profile)
        assert "analytisch" in prompt.lower() or "vergelijkend" in prompt.lower()
        assert "Atlas" in prompt or "atlas" in prompt.lower()

    def test_all_prompts_contain_guardrails(self, all_connectors):
        orch = ChatOrchestrator(connectors=all_connectors)
        for profile in ["patient", "professional", "policymaker"]:
            prompt = orch._build_system_prompt(profile)
            assert "Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd" in prompt
            assert "Je bent een informatieassistent, geen arts" in prompt
            assert "Geef nooit persoonlijk medisch advies" in prompt
            assert "kanker.nl" in prompt or "huisarts" in prompt
            assert "bron" in prompt.lower()


# ---------------------------------------------------------------------------
# Tests: tool definitions
# ---------------------------------------------------------------------------

class TestToolDefinitions:
    """Verify tool definitions match the TSD."""

    def test_tool_count(self, all_connectors):
        orch = ChatOrchestrator(connectors=all_connectors)
        tools = orch._build_tool_definitions()
        # 6 tools: search_kanker_nl, get_cancer_incidence, get_survival_rates,
        # get_stage_distribution, get_regional_cancer_data, search_publications
        assert len(tools) == 6

    def test_tool_names(self, all_connectors):
        orch = ChatOrchestrator(connectors=all_connectors)
        tools = orch._build_tool_definitions()
        names = {t["function"]["name"] for t in tools}
        expected = {
            "search_kanker_nl",
            "get_cancer_incidence",
            "get_survival_rates",
            "get_stage_distribution",
            "get_regional_cancer_data",
            "search_publications",
        }
        assert names == expected

    def test_tools_have_descriptions(self, all_connectors):
        orch = ChatOrchestrator(connectors=all_connectors)
        tools = orch._build_tool_definitions()
        for tool in tools:
            assert "description" in tool["function"]
            assert len(tool["function"]["description"]) > 20


# ---------------------------------------------------------------------------
# Tests: tool dispatch
# ---------------------------------------------------------------------------

class TestToolDispatch:
    """Verify tool calls are dispatched to the correct connector."""

    @pytest.mark.asyncio
    async def test_dispatch_search_kanker_nl(self, all_connectors, kanker_nl_connector):
        orch = ChatOrchestrator(connectors=all_connectors)
        result = await orch._dispatch_tool_call(
            "search_kanker_nl",
            {"query": "borstkanker", "kankersoort": "borstkanker", "section": None},
        )
        kanker_nl_connector.query.assert_awaited_once()
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_dispatch_get_cancer_incidence(self, all_connectors, nkr_connector):
        orch = ChatOrchestrator(connectors=all_connectors)
        result = await orch._dispatch_tool_call(
            "get_cancer_incidence",
            {"cancer_type": "borstkanker", "period": "2020", "sex": None, "age_group": None, "region": None},
        )
        nkr_connector.query.assert_awaited_once()
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_returns_error(self, all_connectors):
        orch = ChatOrchestrator(connectors=all_connectors)
        result = await orch._dispatch_tool_call(
            "nonexistent_tool",
            {"query": "test"},
        )
        assert result.data is None
        assert "niet beschikbaar" in result.summary.lower() or "onbekend" in result.summary.lower()


# ---------------------------------------------------------------------------
# Tests: SSE event generation (full flow)
# ---------------------------------------------------------------------------

class TestSSEEventGeneration:
    """Verify the orchestrator yields SSE events in the correct order."""

    @pytest.mark.asyncio
    async def test_full_flow_yields_correct_events(self, all_connectors, patient_request):
        """
        Simulate: Claude calls search_kanker_nl, gets result, then produces text.
        Expected SSE events: source_card, token(s), done.
        """
        tool_response = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker", "kankersoort": "borstkanker", "section": None},
        )
        final_text = "Borstkanker is de meest voorkomende kankersoort bij vrouwen."
        text_response = _make_text_response(final_text)

        orch = ChatOrchestrator(connectors=all_connectors)

        with patch("orchestrator.litellm") as mock_litellm:
            # First call returns tool_use, second call returns text
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orch.stream(patient_request):
                events.append(event)

        event_types = [e.event for e in events]

        # Must contain source_card after tool call
        assert "source_card" in event_types
        # Must contain token events with the response text
        assert "token" in event_types
        # Must end with done
        assert event_types[-1] == "done"

        # Verify token content
        token_texts = [
            json.loads(e.data)["text"]
            for e in events
            if e.event == "token"
        ]
        combined = "".join(token_texts)
        assert combined == final_text

    @pytest.mark.asyncio
    async def test_chart_data_emitted_for_visualizable_results(self, all_connectors, patient_request):
        """When a connector returns visualizable=True, a chart_data event should be emitted."""
        tool_response = _make_tool_use_response(
            "get_cancer_incidence",
            {"cancer_type": "borstkanker", "period": "2020", "sex": None, "age_group": None, "region": None},
        )
        text_response = _make_text_response("Er waren 15.000 nieuwe gevallen.")

        orch = ChatOrchestrator(connectors=all_connectors)

        with patch("orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orch.stream(patient_request):
                events.append(event)

        event_types = [e.event for e in events]
        assert "chart_data" in event_types

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(self, all_connectors, patient_request):
        """Claude calls two tools before producing a final answer."""
        tool_response_1 = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker", "kankersoort": "borstkanker", "section": None},
            tool_use_id="toolu_01",
        )
        tool_response_2 = _make_tool_use_response(
            "get_cancer_incidence",
            {"cancer_type": "borstkanker", "period": "2020", "sex": None, "age_group": None, "region": None},
            tool_use_id="toolu_02",
        )
        text_response = _make_text_response("Borstkanker is veelvoorkomend met 15.000 gevallen in 2020.")

        orch = ChatOrchestrator(connectors=all_connectors)

        with patch("orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response_1, tool_response_2, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orch.stream(patient_request):
                events.append(event)

        source_cards = [e for e in events if e.event == "source_card"]
        assert len(source_cards) >= 2

    @pytest.mark.asyncio
    async def test_tool_failure_handled_gracefully(self, all_connectors, patient_request, kanker_nl_connector):
        """If a connector raises an exception, the orchestrator catches it and continues."""
        kanker_nl_connector.query = AsyncMock(side_effect=Exception("Connection timeout"))

        tool_response = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker"},
        )
        text_response = _make_text_response("Er is een probleem opgetreden bij het ophalen van informatie.")

        orch = ChatOrchestrator(connectors=all_connectors)

        with patch("orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orch.stream(patient_request):
                events.append(event)

        # Should still complete without raising
        assert any(e.event == "done" for e in events)
