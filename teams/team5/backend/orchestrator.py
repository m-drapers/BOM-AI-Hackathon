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

from models import (
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
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
            ]

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
                    # Append assistant message with tool_calls to conversation
                    assistant_msg: dict[str, Any] = {
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
    cleaned = {k: v for k, v in tool_args.items() if v is not None}

    # For NKR tools, add the 'page' parameter expected by the connector
    if tool_name == "get_cancer_incidence":
        cleaned["page"] = "incidence"
    elif tool_name == "get_survival_rates":
        cleaned["page"] = "survival"
    elif tool_name == "get_stage_distribution":
        cleaned["page"] = "stage-distribution"

    return cleaned


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
