# Cancer Information Chat — Implementation Plan (Part 3: Orchestrator & API)

> Continues from Part 2. See `2026-04-10-cancer-chat-impl-plan-part2.md` for connectors.

---

## Task 9: Chat Orchestrator

**Goal:** Build the orchestrator that takes a `ChatRequest`, calls Claude with tools, dispatches to connectors, and yields SSE events.

**Files:**
- Create: `backend/orchestrator.py`
- Create: `backend/tests/test_orchestrator.py`

---

### Step 9.1 — Write failing test

- [ ] Create `backend/tests/test_orchestrator.py`

```python
# backend/tests/test_orchestrator.py
"""Tests for the chat orchestrator."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.orchestrator import ChatOrchestrator, SSEEvent
from backend.models import ChatRequest, ChatMessage, SourceResult, Citation


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

        with patch("backend.orchestrator.litellm") as mock_litellm:
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

        with patch("backend.orchestrator.litellm") as mock_litellm:
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

        with patch("backend.orchestrator.litellm") as mock_litellm:
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

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orch.stream(patient_request):
                events.append(event)

        # Should still complete without raising
        assert any(e.event == "done" for e in events)
```

- [ ] Run test — expect failure (module not found):

```bash
cd backend && python -m pytest tests/test_orchestrator.py -x -v 2>&1 | head -30
```

---

### Step 9.2 — Implement the orchestrator

- [ ] Create `backend/orchestrator.py`

```python
# backend/orchestrator.py
"""
Chat orchestrator: takes a ChatRequest, calls Claude via LiteLLM with tool-use,
dispatches tool calls to connectors, and yields SSE events.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from typing import AsyncGenerator, Any

import litellm

from backend.models import (
    ChatRequest,
    SourceResult,
    Citation,
    SourceCard,
    ChartData,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSE event dataclass
# ---------------------------------------------------------------------------

@dataclass
class SSEEvent:
    """A single Server-Sent Event to yield to the client."""
    event: str   # "token" | "source_card" | "chart_data" | "done" | "error"
    data: str    # JSON string


# ---------------------------------------------------------------------------
# System prompts per profile (Dutch)
# ---------------------------------------------------------------------------

_GUARDRAILS = """
## Strikte regels

1. Baseer je antwoord uitsluitend op de bronnen die je hebt geraadpleegd. Gebruik NOOIT algemene kennis.
2. Je bent een informatieassistent, geen arts. Geef nooit persoonlijk medisch advies. Verwijs bij persoonlijke medische vragen door naar de huisarts of specialist.
3. Als je geen relevante informatie vindt, zeg dat eerlijk en verwijs door naar kanker.nl of de huisarts. Voorbeeld: "Ik heb hier geen betrouwbare bron voor gevonden. Kijk op kanker.nl of neem contact op met uw huisarts."
4. Vermeld altijd de bron (URL) bij elke claim. Gebruik het formaat: [Brontitel](URL).
5. Verzin nooit URLs, cijfers of feiten. Gebruik alleen wat de tools teruggeven.
6. Antwoord in het Nederlands, tenzij de gebruiker expliciet in een andere taal schrijft.
""".strip()

SYSTEM_PROMPT_PATIENT = f"""
Je bent een vriendelijke en empathische informatieassistent over kanker, ontwikkeld door IKNL.
Je helpt patienten en hun naasten met begrijpelijke, betrouwbare informatie over kanker.

## Toon en stijl
- Schrijf in eenvoudig, helder Nederlands. Vermijd medisch jargon.
- Wees warm en meelevend. Erken dat het een moeilijke situatie kan zijn.
- Geef samenvattingen in toegankelijke taal.
- Als je cijfers noemt, leg ze uit in begrijpelijke termen (bijv. "ongeveer 1 op de 7 vrouwen").

## Bronprioriteit
1. kanker.nl (patiëntinformatie) — raadpleeg dit ALTIJD als eerste.
2. NKR-Cijfers — alleen als de gebruiker specifiek naar cijfers vraagt; vereenvoudig de presentatie.
3. Publicaties — alleen als aanvulling, vereenvoudig de conclusies.
4. Kankeratlas — alleen als de gebruiker naar regionale verschillen vraagt.

{_GUARDRAILS}
""".strip()

SYSTEM_PROMPT_PROFESSIONAL = f"""
Je bent een klinische informatieassistent over kanker, ontwikkeld door IKNL.
Je helpt zorgprofessionals met nauwkeurige, gedetailleerde informatie uit betrouwbare bronnen.

## Toon en stijl
- Schrijf klinisch en precies. Gebruik correcte medische terminologie.
- Presenteer volledige datatabellen, percentages en stadieringsdetails.
- Geef evidenceniveaus aan waar mogelijk.
- Wees bondig maar volledig.

## Bronprioriteit
1. NKR-Cijfers (incidentie, overleving, stadiëring) — primaire bron voor epidemiologische data.
2. Wetenschappelijke publicaties — voor evidence-based klinische context.
3. kanker.nl — als aanvulling voor patiëntgerichte uitleg.
4. Kankeratlas — voor regionale epidemiologische vergelijkingen.

{_GUARDRAILS}
""".strip()

SYSTEM_PROMPT_POLICYMAKER = f"""
Je bent een analytische informatieassistent over kanker, ontwikkeld door IKNL.
Je helpt beleidsmakers met vergelijkende analyses, trends en regionale inzichten.

## Toon en stijl
- Schrijf analytisch en vergelijkend. Focus op trends, patronen en regionale verschillen.
- Presenteer data in een beleidsrelevant kader.
- Gebruik vergelijkingen (regionaal, temporeel, demografisch) waar mogelijk.
- Geef samenvattende conclusies met beleidsimplicaties.

## Bronprioriteit
1. Kankeratlas — primaire bron voor regionale vergelijkingen en SIR-data.
2. NKR-Cijfers — voor landelijke trends en demografische uitsplitsingen.
3. IKNL-rapporten en publicaties — voor diepere analyses en beleidsrelevante conclusies.
4. kanker.nl — als aanvulling voor context over kankersoorten.

{_GUARDRAILS}
""".strip()

_SYSTEM_PROMPTS = {
    "patient": SYSTEM_PROMPT_PATIENT,
    "professional": SYSTEM_PROMPT_PROFESSIONAL,
    "policymaker": SYSTEM_PROMPT_POLICYMAKER,
}

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic / OpenAI function-calling format for LiteLLM)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_kanker_nl",
            "description": (
                "Search the kanker.nl patient information database for general "
                "information about cancer types, diagnosis, treatment options, "
                "side effects, and life after diagnosis. Content is in Dutch. "
                "Optionally filter by cancer type (kankersoort) and section."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query in Dutch",
                    },
                    "kankersoort": {
                        "type": "string",
                        "description": "Optional cancer type filter, e.g. 'borstkanker', 'longkanker'",
                    },
                    "section": {
                        "type": "string",
                        "description": "Optional section filter: 'algemeen', 'diagnose', 'onderzoeken', 'behandelingen', 'gevolgen', 'na-de-uitslag'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cancer_incidence",
            "description": (
                "Query the Netherlands Cancer Registry (NKR) for incidence "
                "(new cases) data. Returns counts and rates per 100,000 for the "
                "requested cancer type, period, and optional demographic filters. "
                "Data is authoritative and covers 1961 to present."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cancer_type": {
                        "type": "string",
                        "description": "Cancer type name or NKR code, e.g. 'borstkanker', 'longkanker'",
                    },
                    "period": {
                        "type": "string",
                        "description": "Year or range, e.g. '2020' or '2015-2020'",
                    },
                    "sex": {
                        "type": "string",
                        "description": "Filter by sex: 'male', 'female', or 'both'",
                    },
                    "age_group": {
                        "type": "string",
                        "description": "Age group filter, e.g. '60-74', '0-14', '75+'",
                    },
                    "region": {
                        "type": "string",
                        "description": "Dutch province name or 'national'",
                    },
                },
                "required": ["cancer_type", "period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_survival_rates",
            "description": (
                "Query the Netherlands Cancer Registry for survival statistics. "
                "Returns 1-year, 5-year, and 10-year relative survival rates for "
                "the specified cancer type and period, with optional sex and age "
                "group filters."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cancer_type": {
                        "type": "string",
                        "description": "Cancer type name, e.g. 'borstkanker', 'colorectaal carcinoom'",
                    },
                    "period": {
                        "type": "string",
                        "description": "Year or range, e.g. '2020' or '2015-2020'",
                    },
                    "sex": {
                        "type": "string",
                        "description": "Filter by sex: 'male', 'female', or 'both'",
                    },
                    "age_group": {
                        "type": "string",
                        "description": "Age group filter, e.g. '60-74'",
                    },
                },
                "required": ["cancer_type", "period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stage_distribution",
            "description": (
                "Query the Netherlands Cancer Registry for stage distribution "
                "data. Returns the percentage breakdown by TNM stage (I, II, III, "
                "IV, Unknown) for the specified cancer type and period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cancer_type": {
                        "type": "string",
                        "description": "Cancer type name, e.g. 'borstkanker'",
                    },
                    "period": {
                        "type": "string",
                        "description": "Year or range, e.g. '2020' or '2015-2020'",
                    },
                    "sex": {
                        "type": "string",
                        "description": "Filter by sex: 'male', 'female', or 'both'",
                    },
                },
                "required": ["cancer_type", "period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_regional_cancer_data",
            "description": (
                "Look up regional cancer incidence data from the IKNL Cancer "
                "Atlas. Returns Standardized Incidence Ratios (SIRs) at postcode "
                "level for 25 cancer groups, showing whether a region has higher "
                "or lower incidence than the national average. Can render as a map."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cancer_type": {
                        "type": "string",
                        "description": "Cancer group name in Dutch, e.g. 'longkanker', 'borstkanker'",
                    },
                    "sex": {
                        "type": "string",
                        "description": "Filter by sex: 'male', 'female', or 'both'",
                    },
                    "postcode": {
                        "type": "string",
                        "description": "3- or 4-digit postcode prefix, e.g. '506' or '5061'",
                    },
                },
                "required": ["cancer_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_publications",
            "description": (
                "Search indexed scientific publications and institutional reports "
                "about cancer. Includes Lancet and ESMO papers (English) and IKNL "
                "reports on gender differences, metastatic cancer, and colorectal "
                "trends (Dutch). Filter by source type or language."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query",
                    },
                    "source_type": {
                        "type": "string",
                        "description": "Filter by type: 'report' or 'publication'",
                    },
                    "language": {
                        "type": "string",
                        "description": "Filter by language: 'nl' or 'en'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool name -> connector name mapping
# ---------------------------------------------------------------------------

_TOOL_TO_CONNECTOR = {
    "search_kanker_nl": "kanker_nl",
    "get_cancer_incidence": "nkr_cijfers",
    "get_survival_rates": "nkr_cijfers",
    "get_stage_distribution": "nkr_cijfers",
    "get_regional_cancer_data": "cancer_atlas",
    "search_publications": "publications",
}

# Maximum number of tool-call loops before forcing a text response
_MAX_TOOL_LOOPS = 10


# ---------------------------------------------------------------------------
# ChatOrchestrator
# ---------------------------------------------------------------------------

class ChatOrchestrator:
    """
    Orchestrates a chat turn: builds the system prompt, calls Claude via LiteLLM,
    dispatches tool calls to connectors, and yields SSE events.
    """

    def __init__(
        self,
        connectors: list,
        model: str = "anthropic/claude-sonnet-4-20250514",
    ):
        self.model = model
        self._connectors = {c.name: c for c in connectors}
        self._sources_tried: list[str] = []
        self._source_cards: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream(self, request: ChatRequest) -> AsyncGenerator[SSEEvent, None]:
        """
        Process a ChatRequest and yield SSE events:
        - source_card: after each tool call completes
        - chart_data: when a tool returns visualizable data
        - token: each text chunk of the final response
        - done: when the response is complete
        - error: if something goes wrong
        """
        message_id = str(uuid.uuid4())

        try:
            system_prompt = self._build_system_prompt(request.profile)

            # Build the messages list for LiteLLM
            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content})

            # Add current user message
            messages.append({"role": "user", "content": request.message})

            tools = self._build_tool_definitions()

            # Tool-use loop: call LLM, dispatch tools, feed results back
            loop_count = 0
            while loop_count < _MAX_TOOL_LOOPS:
                loop_count += 1

                response = await litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    temperature=0.3,
                )

                choice = response.choices[0]

                # Check if Claude wants to call tools
                if choice.message.tool_calls:
                    # Process each tool call
                    # Append assistant message with tool_calls to conversation
                    assistant_msg = {
                        "role": "assistant",
                        "content": choice.message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in choice.message.tool_calls
                        ],
                    }
                    messages.append(assistant_msg)

                    for tool_call in choice.message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}

                        logger.info(f"Tool call: {tool_name}({tool_args})")

                        # Dispatch to connector
                        result = await self._dispatch_tool_call(tool_name, tool_args)

                        # Track sources
                        connector_name = _TOOL_TO_CONNECTOR.get(tool_name, tool_name)
                        if connector_name not in self._sources_tried:
                            self._sources_tried.append(connector_name)

                        # Emit source_card events
                        for source in result.sources:
                            card = {
                                "source": connector_name,
                                "url": source.url,
                                "reliability": source.reliability,
                                "contributed": result.data is not None and result.data != {},
                            }
                            self._source_cards.append(card)
                            yield SSEEvent(
                                event="source_card",
                                data=json.dumps(card, ensure_ascii=False),
                            )

                        # Emit source_card for connectors that returned no sources
                        if not result.sources and connector_name not in [
                            c["source"] for c in self._source_cards
                        ]:
                            card = {
                                "source": connector_name,
                                "url": "",
                                "reliability": "",
                                "contributed": False,
                            }
                            self._source_cards.append(card)
                            yield SSEEvent(
                                event="source_card",
                                data=json.dumps(card, ensure_ascii=False),
                            )

                        # Emit chart_data if visualizable
                        if result.visualizable and result.data:
                            chart = _build_chart_data(tool_name, result)
                            if chart:
                                yield SSEEvent(
                                    event="chart_data",
                                    data=json.dumps(chart, ensure_ascii=False),
                                )

                        # Add tool result to messages for Claude
                        tool_result_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({
                                "summary": result.summary,
                                "data": result.data,
                                "sources": [
                                    {"url": s.url, "title": s.title}
                                    for s in result.sources
                                ],
                            }, ensure_ascii=False),
                        }
                        messages.append(tool_result_msg)

                    # Continue loop to let Claude process tool results
                    continue

                # Claude produced a final text response
                final_text = choice.message.content or ""

                # Yield token events (split into chunks for streaming feel)
                chunk_size = 20  # characters per token event
                for i in range(0, len(final_text), chunk_size):
                    chunk = final_text[i:i + chunk_size]
                    yield SSEEvent(
                        event="token",
                        data=json.dumps({"text": chunk}, ensure_ascii=False),
                    )

                # Done
                yield SSEEvent(
                    event="done",
                    data=json.dumps({
                        "message_id": message_id,
                        "sources_tried": self._sources_tried,
                    }, ensure_ascii=False),
                )
                return

            # Exceeded max tool loops — force completion
            yield SSEEvent(
                event="token",
                data=json.dumps({
                    "text": "Ik heb meerdere bronnen geraadpleegd maar kon geen definitief antwoord samenstellen. Probeer uw vraag specifieker te stellen.",
                }, ensure_ascii=False),
            )
            yield SSEEvent(
                event="done",
                data=json.dumps({
                    "message_id": message_id,
                    "sources_tried": self._sources_tried,
                }, ensure_ascii=False),
            )

        except Exception as exc:
            logger.exception("Orchestrator error")
            yield SSEEvent(
                event="error",
                data=json.dumps({
                    "code": "orchestrator_error",
                    "message": f"Er is een fout opgetreden: {str(exc)}",
                }, ensure_ascii=False),
            )
            yield SSEEvent(
                event="done",
                data=json.dumps({
                    "message_id": message_id,
                    "sources_tried": self._sources_tried,
                }, ensure_ascii=False),
            )

    # ------------------------------------------------------------------
    # Internal: build system prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, profile: str) -> str:
        """Return the system prompt for the given user profile."""
        return _SYSTEM_PROMPTS.get(profile, SYSTEM_PROMPT_PATIENT)

    # ------------------------------------------------------------------
    # Internal: build tool definitions
    # ------------------------------------------------------------------

    def _build_tool_definitions(self) -> list[dict]:
        """Return the tool definitions array for LiteLLM."""
        return TOOL_DEFINITIONS

    # ------------------------------------------------------------------
    # Internal: dispatch a tool call to the right connector
    # ------------------------------------------------------------------

    async def _dispatch_tool_call(self, tool_name: str, tool_args: dict) -> SourceResult:
        """
        Dispatch a tool call to the appropriate connector.
        Returns a SourceResult (never raises).
        """
        connector_name = _TOOL_TO_CONNECTOR.get(tool_name)
        if connector_name is None or connector_name not in self._connectors:
            return SourceResult(
                data=None,
                summary=f"Tool '{tool_name}' is niet beschikbaar.",
                sources=[],
                visualizable=False,
            )

        connector = self._connectors[connector_name]

        try:
            # Map tool arguments to connector query parameters
            query_params = _map_tool_args_to_query_params(tool_name, tool_args)
            result = await connector.query(**query_params)
            return result
        except Exception as exc:
            logger.exception(f"Connector {connector_name} failed for tool {tool_name}")
            return SourceResult(
                data=None,
                summary=f"Fout bij het raadplegen van {connector_name}: {str(exc)}",
                sources=[],
                visualizable=False,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_tool_args_to_query_params(tool_name: str, tool_args: dict) -> dict:
    """
    Map Claude's tool call arguments to the connector's query() parameters.
    Strips None values so connectors receive only explicitly provided filters.
    """
    # Remove None values
    return {k: v for k, v in tool_args.items() if v is not None}


def _build_chart_data(tool_name: str, result: SourceResult) -> dict | None:
    """
    Build a chart_data payload from a visualizable SourceResult.
    Returns None if the data is not suitable for charting.
    """
    data = result.data
    if not data:
        return None

    if tool_name == "get_cancer_incidence":
        # Expect data with incidence list
        items = data if isinstance(data, list) else data.get("incidence", [])
        if not items:
            return None
        return {
            "type": "line",
            "title": "Incidentie (nieuwe gevallen)",
            "data": items if isinstance(items, list) else [items],
            "x_key": "year",
            "y_key": "count",
            "unit": "gevallen",
        }

    if tool_name == "get_survival_rates":
        items = data if isinstance(data, list) else data.get("survival", [])
        if not items:
            return None
        return {
            "type": "line",
            "title": "Overlevingspercentages",
            "data": items if isinstance(items, list) else [items],
            "x_key": "years",
            "y_key": "rate",
            "unit": "%",
        }

    if tool_name == "get_stage_distribution":
        items = data if isinstance(data, list) else data.get("stages", [])
        if not items:
            return None
        return {
            "type": "bar",
            "title": "Stadiumverdeling",
            "data": items if isinstance(items, list) else [items],
            "x_key": "stage",
            "y_key": "percentage",
            "unit": "%",
        }

    if tool_name == "get_regional_cancer_data":
        items = data if isinstance(data, list) else data.get("regions", [])
        if not items:
            return None
        return {
            "type": "bar",
            "title": "Regionale SIR-waarden",
            "data": items if isinstance(items, list) else [items],
            "x_key": "region",
            "y_key": "sir",
            "unit": "SIR",
        }

    return None
```

- [ ] Run tests — expect pass:

```bash
cd backend && python -m pytest tests/test_orchestrator.py -x -v
```

---

### Step 9.3 — Verify and commit

- [ ] Confirm all 14 tests in `test_orchestrator.py` pass
- [ ] Commit:

```bash
git add backend/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: add chat orchestrator with tool-use loop and SSE events (Task 9)"
```

---

## Task 10: FastAPI Application + SSE Endpoint

**Goal:** Build the FastAPI app with SSE streaming chat, feedback storage, health check, and CORS.

**Files:**
- Create: `backend/main.py`
- Create: `backend/tests/test_api.py`

---

### Step 10.1 — Write failing test

- [ ] Create `backend/tests/test_api.py`

```python
# backend/tests/test_api.py
"""Tests for the FastAPI application."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.main import app, get_orchestrator
from backend.orchestrator import SSEEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator that yields predefined SSE events."""
    async def mock_stream(request):
        yield SSEEvent(
            event="source_card",
            data=json.dumps({
                "source": "kanker_nl",
                "url": "https://www.kanker.nl/borstkanker",
                "reliability": "patient-info",
                "contributed": True,
            }),
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
            data=json.dumps({
                "message_id": "msg-001",
                "sources_tried": ["kanker_nl"],
            }),
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
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        with patch("backend.main.FEEDBACK_DB_PATH", str(tmp_path / "test_feedback.db")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        with patch("backend.main.FEEDBACK_DB_PATH", str(tmp_path / "test_feedback.db")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
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
            async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        with patch("backend.main._create_orchestrator", return_value=mock_orchestrator):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        async with AsyncClient(transport=transport, base_url="http://test") as client:
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
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "message": "Test",
                "session_id": "sess-001",
                "profile": "invalid_profile",
                "history": [],
            }
            response = await client.post("/api/chat/stream", json=payload)

        assert response.status_code == 422
```

- [ ] Run test — expect failure (module not found):

```bash
cd backend && python -m pytest tests/test_api.py -x -v 2>&1 | head -30
```

---

### Step 10.2 — Implement the FastAPI app

- [ ] Create `backend/main.py`

```python
# backend/main.py
"""
FastAPI application for the Cancer Information Chat system.

Endpoints:
- POST /api/chat/stream — SSE streaming chat
- POST /api/feedback — store user feedback
- GET  /api/feedback/export — export feedback as CSV
- GET  /api/health — health check
"""
import csv
import io
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.models import ChatRequest, FeedbackEntry
from backend.orchestrator import ChatOrchestrator, SSEEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FEEDBACK_DB_PATH = os.environ.get("FEEDBACK_DB_PATH", "data/feedback.db")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.environ.get(
    "LLM_MODEL",
    "anthropic/claude-sonnet-4-20250514",
)
CHROMADB_PATH = os.environ.get("CHROMADB_PATH", "data/chromadb")
VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Connector + orchestrator initialization
# ---------------------------------------------------------------------------

# Global connectors list — populated at startup
_connectors: list = []


def _create_orchestrator() -> ChatOrchestrator:
    """Create a new ChatOrchestrator with the current connectors."""
    return ChatOrchestrator(connectors=_connectors, model=LLM_MODEL)


def _init_connectors() -> list:
    """
    Initialize all source connectors.
    Returns a list of connector instances.
    Called once at startup.
    """
    connectors = []

    try:
        from backend.connectors.kanker_nl import KankerNlConnector
        connectors.append(KankerNlConnector(chromadb_path=CHROMADB_PATH))
        logger.info("Loaded kanker_nl connector")
    except Exception as exc:
        logger.warning(f"Could not load kanker_nl connector: {exc}")

    try:
        from backend.connectors.nkr_cijfers import NkrCijfersConnector
        connectors.append(NkrCijfersConnector())
        logger.info("Loaded nkr_cijfers connector")
    except Exception as exc:
        logger.warning(f"Could not load nkr_cijfers connector: {exc}")

    try:
        from backend.connectors.cancer_atlas import CancerAtlasConnector
        connectors.append(CancerAtlasConnector())
        logger.info("Loaded cancer_atlas connector")
    except Exception as exc:
        logger.warning(f"Could not load cancer_atlas connector: {exc}")

    try:
        from backend.connectors.publications import PublicationsConnector
        connectors.append(PublicationsConnector(chromadb_path=CHROMADB_PATH))
        logger.info("Loaded publications connector")
    except Exception as exc:
        logger.warning(f"Could not load publications connector: {exc}")

    return connectors


def _check_chromadb_collections() -> list[str]:
    """Check which ChromaDB collections exist. Returns list of collection names."""
    collections = []
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        for col in client.list_collections():
            collections.append(col.name if hasattr(col, "name") else str(col))
    except Exception as exc:
        logger.warning(f"Could not check ChromaDB collections: {exc}")
    return collections


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize connectors and check ChromaDB on startup."""
    global _connectors
    logger.info("Starting up Cancer Information Chat backend...")

    # Initialize connectors (graceful — missing connectors are logged, not fatal)
    _connectors = _init_connectors()
    logger.info(f"Loaded {len(_connectors)} connectors: {[c.name for c in _connectors]}")

    # Check ChromaDB collections
    collections = _check_chromadb_collections()
    logger.info(f"ChromaDB collections found: {collections}")

    yield

    logger.info("Shutting down...")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Cancer Information Chat API",
    description="IKNL Hackathon — Chat interface over trusted cancer information sources",
    version=VERSION,
    lifespan=lifespan,
)

# CORS — allow all origins for hackathon
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SQLite feedback helpers
# ---------------------------------------------------------------------------

async def _ensure_feedback_table(db_path: str) -> None:
    """Create the feedback table if it does not exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                rating TEXT NOT NULL,
                comment TEXT,
                query TEXT NOT NULL,
                sources_tried TEXT NOT NULL,
                profile TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        await db.commit()


async def _store_feedback(db_path: str, entry: FeedbackEntry) -> str:
    """Store a feedback entry and return its ID."""
    await _ensure_feedback_table(db_path)

    feedback_id = str(uuid.uuid4())
    timestamp = (entry.timestamp or datetime.now(timezone.utc)).isoformat()

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO feedback (id, session_id, message_id, rating, comment, query, sources_tried, profile, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                entry.session_id,
                entry.message_id,
                entry.rating,
                entry.comment,
                entry.query,
                json.dumps(entry.sources_tried),
                entry.profile,
                timestamp,
            ),
        )
        await db.commit()

    return feedback_id


async def _export_feedback_csv(db_path: str) -> str:
    """Export all feedback as CSV string."""
    await _ensure_feedback_table(db_path)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM feedback ORDER BY timestamp DESC") as cursor:
            rows = await cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "session_id", "message_id", "rating", "comment",
        "query", "sources_tried", "profile", "timestamp",
    ])
    for row in rows:
        writer.writerow([
            row["id"],
            row["session_id"],
            row["message_id"],
            row["rating"],
            row["comment"],
            row["query"],
            row["sources_tried"],
            row["profile"],
            row["timestamp"],
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    collections = _check_chromadb_collections()
    status = "healthy" if len(_connectors) > 0 else "degraded"

    return {
        "status": status,
        "llm_provider": LLM_PROVIDER,
        "chromadb_collections": collections,
        "connectors_loaded": [c.name for c in _connectors],
        "version": VERSION,
    }


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE streaming chat endpoint.
    Accepts a ChatRequest and returns a stream of Server-Sent Events.
    """
    orchestrator = _create_orchestrator()

    async def event_generator():
        async for sse_event in orchestrator.stream(request):
            yield {
                "event": sse_event.event,
                "data": sse_event.data,
            }

    return EventSourceResponse(event_generator())


@app.post("/api/feedback", status_code=201)
async def submit_feedback(entry: FeedbackEntry):
    """Store user feedback on a chat response."""
    feedback_id = await _store_feedback(FEEDBACK_DB_PATH, entry)
    return {"id": feedback_id}


@app.get("/api/feedback/export")
async def export_feedback():
    """Export all feedback entries as CSV."""
    csv_content = await _export_feedback_csv(FEEDBACK_DB_PATH)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="feedback-export.csv"',
        },
    )
```

- [ ] Run tests — expect pass:

```bash
cd backend && python -m pytest tests/test_api.py -x -v
```

---

### Step 10.3 — Verify and commit

- [ ] Confirm all 7 tests in `test_api.py` pass
- [ ] Commit:

```bash
git add backend/main.py backend/tests/test_api.py
git commit -m "feat: add FastAPI app with SSE chat, feedback, and health endpoints (Task 10)"
```

---

## Task 11: Integration Test — Full Pipeline

**Goal:** Smoke test the full pipeline: question -> orchestrator -> connector -> response with citations.

**Files:**
- Create: `backend/tests/test_integration.py`

---

### Step 11.1 — Write the integration test

- [ ] Create `backend/tests/test_integration.py`

```python
# backend/tests/test_integration.py
"""
Integration test: full pipeline smoke test.

Tests the complete flow:
  question -> orchestrator -> tool selection -> connector query -> response with citations

Uses a temporary ChromaDB with a small subset of test data and a mocked LLM
that returns predictable tool calls + responses.
"""
import json
import os
import tempfile
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import ChatRequest, ChatMessage, SourceResult, Citation
from backend.orchestrator import ChatOrchestrator, SSEEvent


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

KANKER_NL_TEST_DOCS = [
    {
        "id": "doc-001",
        "text": (
            "Borstkanker is de meest voorkomende vorm van kanker bij vrouwen in Nederland. "
            "Jaarlijks krijgen ongeveer 15.000 vrouwen de diagnose borstkanker. "
            "De meeste vrouwen die borstkanker krijgen zijn ouder dan 50 jaar."
        ),
        "metadata": {
            "kankersoort": "borstkanker",
            "section": "algemeen",
            "url": "https://www.kanker.nl/kankersoorten/borstkanker/algemeen",
            "title": "Borstkanker - Algemeen",
        },
    },
    {
        "id": "doc-002",
        "text": (
            "De behandeling van borstkanker hangt af van het stadium, het type en de "
            "eigenschappen van de tumor. Mogelijke behandelingen zijn operatie, "
            "bestraling, chemotherapie, hormoontherapie en doelgerichte therapie."
        ),
        "metadata": {
            "kankersoort": "borstkanker",
            "section": "behandelingen",
            "url": "https://www.kanker.nl/kankersoorten/borstkanker/behandelingen",
            "title": "Borstkanker - Behandelingen",
        },
    },
    {
        "id": "doc-003",
        "text": (
            "Longkanker is een kwaadaardige tumor in de long. Het is een van de meest "
            "voorkomende vormen van kanker in Nederland. Roken is de belangrijkste "
            "risicofactor voor longkanker."
        ),
        "metadata": {
            "kankersoort": "longkanker",
            "section": "algemeen",
            "url": "https://www.kanker.nl/kankersoorten/longkanker/algemeen",
            "title": "Longkanker - Algemeen",
        },
    },
]

PUBLICATIONS_TEST_DOCS = [
    {
        "id": "pub-001",
        "text": (
            "This study examined the impact of comorbidities on cancer survival across "
            "eight major cancer types. Results show that patients with cardiovascular "
            "comorbidities had significantly lower 5-year survival rates."
        ),
        "metadata": {
            "source_type": "publication",
            "title": "Comorbidities and survival in 8 cancers",
            "language": "en",
            "topic": "comorbidities",
        },
    },
    {
        "id": "pub-002",
        "text": (
            "Uit het rapport blijkt dat er significante genderverschillen bestaan in de "
            "incidentie van verschillende kankersoorten. Mannen hebben een hoger risico "
            "op long- en blaaskanker, terwijl schildklierkanker vaker bij vrouwen voorkomt."
        ),
        "metadata": {
            "source_type": "report",
            "title": "Genderverschillen bij kanker",
            "language": "nl",
            "topic": "gender differences",
        },
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_chromadb_dir():
    """Create a temporary directory for ChromaDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def populated_chromadb(temp_chromadb_dir):
    """Create a ChromaDB with test data."""
    import chromadb

    client = chromadb.PersistentClient(path=temp_chromadb_dir)

    # Create kanker_nl collection
    kanker_nl = client.get_or_create_collection(
        name="kanker_nl",
        metadata={"description": "kanker.nl patient information"},
    )
    kanker_nl.add(
        ids=[d["id"] for d in KANKER_NL_TEST_DOCS],
        documents=[d["text"] for d in KANKER_NL_TEST_DOCS],
        metadatas=[d["metadata"] for d in KANKER_NL_TEST_DOCS],
    )

    # Create publications collection
    publications = client.get_or_create_collection(
        name="publications",
        metadata={"description": "Scientific publications and reports"},
    )
    publications.add(
        ids=[d["id"] for d in PUBLICATIONS_TEST_DOCS],
        documents=[d["text"] for d in PUBLICATIONS_TEST_DOCS],
        metadatas=[d["metadata"] for d in PUBLICATIONS_TEST_DOCS],
    )

    return temp_chromadb_dir


@pytest.fixture
def kanker_nl_connector(populated_chromadb):
    """Create a kanker_nl connector backed by the test ChromaDB."""
    import chromadb

    client = chromadb.PersistentClient(path=populated_chromadb)
    collection = client.get_collection("kanker_nl")

    async def query_kanker_nl(**params):
        query_text = params.get("query", "")
        where_filter = None
        where_clauses = []

        if params.get("kankersoort"):
            where_clauses.append({"kankersoort": {"$eq": params["kankersoort"]}})
        if params.get("section"):
            where_clauses.append({"section": {"$eq": params["section"]}})

        if len(where_clauses) > 1:
            where_filter = {"$and": where_clauses}
        elif len(where_clauses) == 1:
            where_filter = where_clauses[0]

        results = collection.query(
            query_texts=[query_text],
            where=where_filter,
            n_results=3,
        )

        if not results["documents"][0]:
            return SourceResult(
                data=None,
                summary="Geen relevante informatie gevonden op kanker.nl.",
                sources=[],
                visualizable=False,
            )

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        combined_text = "\n\n".join(docs)

        sources = [
            Citation(
                url=m["url"],
                title=m["title"],
                reliability="patient-info",
            )
            for m in metas
        ]

        return SourceResult(
            data={"text": combined_text, "chunks": len(docs)},
            summary=docs[0][:200],
            sources=sources,
            visualizable=False,
        )

    connector = MagicMock()
    connector.name = "kanker_nl"
    connector.description = "Search kanker.nl patient information."
    connector.query = query_kanker_nl
    return connector


@pytest.fixture
def nkr_connector():
    """Create a mock NKR connector with realistic responses."""
    async def query_nkr(**params):
        cancer_type = params.get("cancer_type", "onbekend")
        period = params.get("period", "2020")
        return SourceResult(
            data={
                "incidence": [
                    {"year": 2018, "count": 14800},
                    {"year": 2019, "count": 14900},
                    {"year": 2020, "count": 15000},
                ],
            },
            summary=f"In {period} waren er circa 15.000 nieuwe gevallen van {cancer_type}.",
            sources=[Citation(
                url=f"https://nkr-cijfers.iknl.nl/viewer/{cancer_type}",
                title=f"NKR-Cijfers: {cancer_type} incidentie",
                reliability="official",
            )],
            visualizable=True,
        )

    connector = MagicMock()
    connector.name = "nkr_cijfers"
    connector.description = "Query the Netherlands Cancer Registry."
    connector.query = query_nkr
    return connector


@pytest.fixture
def atlas_connector():
    """Create a mock Cancer Atlas connector."""
    async def query_atlas(**params):
        return SourceResult(
            data={"sir": 1.05, "p10": 0.95, "p90": 1.15},
            summary="De SIR voor deze regio is 1.05, dicht bij het landelijk gemiddelde.",
            sources=[Citation(
                url="https://kankeratlas.iknl.nl/",
                title="IKNL Kankeratlas",
                reliability="official",
            )],
            visualizable=True,
        )

    connector = MagicMock()
    connector.name = "cancer_atlas"
    connector.description = "Look up regional cancer incidence data."
    connector.query = query_atlas
    return connector


@pytest.fixture
def publications_connector(populated_chromadb):
    """Create a publications connector backed by the test ChromaDB."""
    import chromadb

    client = chromadb.PersistentClient(path=populated_chromadb)
    collection = client.get_collection("publications")

    async def query_publications(**params):
        query_text = params.get("query", "")
        where_filter = None
        where_clauses = []

        if params.get("source_type"):
            where_clauses.append({"source_type": {"$eq": params["source_type"]}})
        if params.get("language"):
            where_clauses.append({"language": {"$eq": params["language"]}})

        if len(where_clauses) > 1:
            where_filter = {"$and": where_clauses}
        elif len(where_clauses) == 1:
            where_filter = where_clauses[0]

        results = collection.query(
            query_texts=[query_text],
            where=where_filter,
            n_results=2,
        )

        if not results["documents"][0]:
            return SourceResult(
                data=None,
                summary="Geen relevante publicaties gevonden.",
                sources=[],
                visualizable=False,
            )

        docs = results["documents"][0]
        metas = results["metadatas"][0]

        sources = [
            Citation(
                url=f"publications/{m['title'].lower().replace(' ', '-')}",
                title=m["title"],
                reliability="peer-reviewed" if m["source_type"] == "publication" else "institutional",
            )
            for m in metas
        ]

        return SourceResult(
            data={"text": "\n\n".join(docs), "chunks": len(docs)},
            summary=docs[0][:200],
            sources=sources,
            visualizable=False,
        )

    connector = MagicMock()
    connector.name = "publications"
    connector.description = "Search scientific publications and reports."
    connector.query = query_publications
    return connector


@pytest.fixture
def all_connectors(kanker_nl_connector, nkr_connector, atlas_connector, publications_connector):
    return [kanker_nl_connector, nkr_connector, atlas_connector, publications_connector]


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_use_id: str = "toolu_int_01"):
    """Create a mock LiteLLM response requesting a tool call."""
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


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Smoke tests for the full pipeline: question -> tool -> connector -> response."""

    @pytest.mark.asyncio
    async def test_patient_question_about_borstkanker(self, all_connectors):
        """
        Scenario: A patient asks "Wat is borstkanker?"
        Expected: Claude calls search_kanker_nl, gets ChromaDB results,
                  produces a response with citations.
        """
        request = ChatRequest(
            message="Wat is borstkanker?",
            session_id="integration-001",
            profile="patient",
            history=[],
        )

        # Mock LLM: first calls search_kanker_nl, then produces text
        tool_response = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker", "kankersoort": "borstkanker"},
        )
        final_text = (
            "Borstkanker is de meest voorkomende vorm van kanker bij vrouwen in Nederland. "
            "Jaarlijks krijgen ongeveer 15.000 vrouwen deze diagnose. "
            "[Bron: Kanker.nl](https://www.kanker.nl/kankersoorten/borstkanker/algemeen)"
        )
        text_response = _make_text_response(final_text)

        orchestrator = ChatOrchestrator(connectors=all_connectors)

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orchestrator.stream(request):
                events.append(event)

        # Verify event sequence
        event_types = [e.event for e in events]
        assert "source_card" in event_types, "Should emit source_card after tool call"
        assert "token" in event_types, "Should emit token events with response text"
        assert event_types[-1] == "done", "Should end with done event"

        # Verify source_card contains kanker.nl citation
        source_cards = [
            json.loads(e.data) for e in events if e.event == "source_card"
        ]
        assert any(
            card["source"] == "kanker_nl" for card in source_cards
        ), "Should have a kanker_nl source card"
        assert any(
            "kanker.nl" in card["url"] for card in source_cards
        ), "Source card should contain kanker.nl URL"

        # Verify response text contains citation
        token_texts = [
            json.loads(e.data)["text"] for e in events if e.event == "token"
        ]
        combined_response = "".join(token_texts)
        assert "borstkanker" in combined_response.lower()
        assert "kanker.nl" in combined_response

        # Verify done event contains sources_tried
        done_event = json.loads(events[-1].data)
        assert "kanker_nl" in done_event["sources_tried"]

    @pytest.mark.asyncio
    async def test_multi_source_query(self, all_connectors):
        """
        Scenario: A professional asks about incidence AND treatment.
        Expected: Claude calls both search_kanker_nl and get_cancer_incidence.
        """
        request = ChatRequest(
            message="Wat is de incidentie van borstkanker en wat zijn de behandelingen?",
            session_id="integration-002",
            profile="professional",
            history=[],
        )

        tool_response_1 = _make_tool_use_response(
            "get_cancer_incidence",
            {"cancer_type": "borstkanker", "period": "2020"},
            tool_use_id="toolu_multi_01",
        )
        tool_response_2 = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker behandelingen", "kankersoort": "borstkanker", "section": "behandelingen"},
            tool_use_id="toolu_multi_02",
        )
        final_text = (
            "In 2020 waren er circa 15.000 nieuwe gevallen van borstkanker (NKR-Cijfers). "
            "Behandelingen omvatten operatie, bestraling en chemotherapie (kanker.nl)."
        )
        text_response = _make_text_response(final_text)

        orchestrator = ChatOrchestrator(connectors=all_connectors)

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response_1, tool_response_2, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orchestrator.stream(request):
                events.append(event)

        # Verify multiple source cards from different connectors
        source_cards = [
            json.loads(e.data) for e in events if e.event == "source_card"
        ]
        sources_used = {card["source"] for card in source_cards}
        assert "nkr_cijfers" in sources_used, "Should have queried NKR-Cijfers"
        assert "kanker_nl" in sources_used, "Should have queried kanker.nl"

        # Verify chart_data emitted for NKR data (visualizable=True)
        chart_events = [e for e in events if e.event == "chart_data"]
        assert len(chart_events) >= 1, "Should emit chart_data for incidence data"

        # Verify done event lists both sources
        done_event = json.loads(events[-1].data)
        assert "nkr_cijfers" in done_event["sources_tried"]
        assert "kanker_nl" in done_event["sources_tried"]

    @pytest.mark.asyncio
    async def test_policymaker_regional_query(self, all_connectors):
        """
        Scenario: A policymaker asks about regional differences.
        Expected: Claude calls get_regional_cancer_data.
        """
        request = ChatRequest(
            message="Hoe verschilt de incidentie van longkanker per regio?",
            session_id="integration-003",
            profile="policymaker",
            history=[],
        )

        tool_response = _make_tool_use_response(
            "get_regional_cancer_data",
            {"cancer_type": "longkanker", "sex": "both"},
            tool_use_id="toolu_region_01",
        )
        final_text = (
            "De SIR voor longkanker in deze regio is 1.05, dicht bij het landelijk gemiddelde. "
            "[Bron: IKNL Kankeratlas](https://kankeratlas.iknl.nl/)"
        )
        text_response = _make_text_response(final_text)

        orchestrator = ChatOrchestrator(connectors=all_connectors)

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orchestrator.stream(request):
                events.append(event)

        source_cards = [
            json.loads(e.data) for e in events if e.event == "source_card"
        ]
        assert any(
            card["source"] == "cancer_atlas" for card in source_cards
        ), "Should have a cancer_atlas source card"

        # Verify analytical system prompt was used (policymaker profile)
        done_event = json.loads(events[-1].data)
        assert "cancer_atlas" in done_event["sources_tried"]

    @pytest.mark.asyncio
    async def test_conversation_with_history(self, all_connectors):
        """
        Scenario: A follow-up question with conversation history.
        Expected: The orchestrator includes history in the LLM call.
        """
        request = ChatRequest(
            message="En wat zijn de overlevingscijfers?",
            session_id="integration-004",
            profile="patient",
            history=[
                ChatMessage(role="user", content="Wat is borstkanker?"),
                ChatMessage(
                    role="assistant",
                    content="Borstkanker is de meest voorkomende kanker bij vrouwen.",
                ),
            ],
        )

        tool_response = _make_tool_use_response(
            "get_survival_rates",
            {"cancer_type": "borstkanker", "period": "2020"},
        )
        # NKR connector doesn't have a get_survival_rates handler,
        # so it will dispatch to nkr_cijfers connector
        final_text = "De 5-jaarsoverleving voor borstkanker is circa 88%."
        text_response = _make_text_response(final_text)

        orchestrator = ChatOrchestrator(connectors=all_connectors)

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orchestrator.stream(request):
                events.append(event)

            # Verify LLM was called with history
            call_args = mock_litellm.acompletion.call_args_list[0]
            messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))

            # Should have: system + 2 history messages + current user message = 4
            user_messages = [m for m in messages if m["role"] == "user"]
            assistant_messages = [m for m in messages if m["role"] == "assistant"]
            assert len(user_messages) == 2, "Should include history user message + current"
            assert len(assistant_messages) == 1, "Should include history assistant message"

    @pytest.mark.asyncio
    async def test_connector_failure_does_not_crash_pipeline(self, all_connectors, kanker_nl_connector):
        """
        Scenario: kanker_nl connector throws an exception.
        Expected: The orchestrator handles it gracefully and still completes.
        """
        # Make the kanker_nl connector fail
        async def failing_query(**params):
            raise ConnectionError("ChromaDB connection lost")

        kanker_nl_connector.query = failing_query

        request = ChatRequest(
            message="Wat is borstkanker?",
            session_id="integration-005",
            profile="patient",
            history=[],
        )

        tool_response = _make_tool_use_response(
            "search_kanker_nl",
            {"query": "borstkanker"},
        )
        final_text = "Er is helaas een probleem opgetreden bij het ophalen van informatie van kanker.nl."
        text_response = _make_text_response(final_text)

        orchestrator = ChatOrchestrator(connectors=all_connectors)

        with patch("backend.orchestrator.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, text_response]
            )

            events: list[SSEEvent] = []
            async for event in orchestrator.stream(request):
                events.append(event)

        # Should still complete without raising
        event_types = [e.event for e in events]
        assert "done" in event_types, "Pipeline should complete even if connector fails"

        # The error should be fed back to Claude as a tool result
        # so it can explain the problem to the user
        assert any(e.event == "token" for e in events), "Should still produce text response"


class TestChromaDBIntegration:
    """Test that the ChromaDB-backed connectors actually retrieve correct data."""

    @pytest.mark.asyncio
    async def test_kanker_nl_retrieves_borstkanker(self, kanker_nl_connector):
        """Verify the kanker_nl connector retrieves borstkanker content from ChromaDB."""
        result = await kanker_nl_connector.query(
            query="Wat is borstkanker?",
            kankersoort="borstkanker",
        )

        assert result.data is not None
        assert "borstkanker" in result.summary.lower()
        assert len(result.sources) > 0
        assert any("kanker.nl" in s.url for s in result.sources)

    @pytest.mark.asyncio
    async def test_kanker_nl_filters_by_section(self, kanker_nl_connector):
        """Verify section filtering works."""
        result = await kanker_nl_connector.query(
            query="behandeling borstkanker",
            kankersoort="borstkanker",
            section="behandelingen",
        )

        assert result.data is not None
        assert len(result.sources) > 0
        # Should prioritize the behandelingen page
        assert any("behandelingen" in s.url for s in result.sources)

    @pytest.mark.asyncio
    async def test_publications_retrieves_english(self, publications_connector):
        """Verify the publications connector retrieves English papers."""
        result = await publications_connector.query(
            query="comorbidities cancer survival",
            language="en",
        )

        assert result.data is not None
        assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_publications_retrieves_dutch(self, publications_connector):
        """Verify the publications connector retrieves Dutch reports."""
        result = await publications_connector.query(
            query="genderverschillen kanker",
            language="nl",
        )

        assert result.data is not None
        assert len(result.sources) > 0
```

- [ ] Run tests — expect pass:

```bash
cd backend && python -m pytest tests/test_integration.py -x -v
```

---

### Step 11.2 — Verify and commit

- [ ] Confirm all 9 integration tests pass
- [ ] Commit:

```bash
git add backend/tests/test_integration.py
git commit -m "feat: add full pipeline integration tests (Task 11)"
```

---

## Summary: Part 3 file inventory

| Task | File | Purpose |
|------|------|---------|
| 9 | `backend/orchestrator.py` | Chat orchestrator with Claude tool-use, system prompts, SSE events |
| 9 | `backend/tests/test_orchestrator.py` | Unit tests for orchestrator (14 tests) |
| 10 | `backend/main.py` | FastAPI app with SSE chat, feedback, health endpoints |
| 10 | `backend/tests/test_api.py` | API endpoint tests (7 tests) |
| 11 | `backend/tests/test_integration.py` | Full pipeline smoke tests (9 tests) |

## Dependencies required (add to `pyproject.toml`)

```toml
[project]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]",
    "sse-starlette>=1.6",
    "litellm>=1.30",
    "anthropic>=0.25",
    "chromadb>=0.5",
    "aiosqlite>=0.19",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]
```

## Run all Part 3 tests

```bash
cd backend && python -m pytest tests/test_orchestrator.py tests/test_api.py tests/test_integration.py -v
```

---

> **Next:** Part 4 covers the frontend (Tasks 12-14).
