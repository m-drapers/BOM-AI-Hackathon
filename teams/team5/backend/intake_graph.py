"""
LangGraph-based intake flow with step-specific agents.

Each step has its own system prompt and constraints.
The graph routes based on what fields are filled in the GegevensModel.
"""

import json
import logging
from typing import Any, Literal

import litellm
from langgraph.graph import StateGraph, END

from models import GegevensModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class IntakeState(dict):
    """State carried through the graph. Plain dict for LangGraph compatibility."""
    pass


# ---------------------------------------------------------------------------
# Step-specific prompts — each node has its own constraints
# ---------------------------------------------------------------------------

STEP_PROMPTS = {
    "bekendheid": """Je bent een vriendelijke assistent. De gebruiker begint net een gesprek.
Je ENIGE taak nu: bepaal hoe bekend de gebruiker is met AI-chatbots.

De gebruiker zegt: "{message}"

Probeer uit het bericht af te leiden of de gebruiker ervaring heeft met AI:
- Als ze zeggen dat ze het niet kennen, of als het hun eerste keer lijkt → "niet_bekend"
- Als ze enige ervaring suggereren → "enigszins"
- Als ze duidelijk ervaren zijn, technische taal gebruiken → "erg_bekend"
- Als je het niet kunt afleiden → null

Als de gebruiker MEER informatie geeft (wie ze zijn, een vraag), vul dat ook in.

Antwoord ALLEEN in JSON:
{{"ai_bekendheid": "..." of null, "gebruiker_type": "..." of null, "vraag_tekst": "..." of null, "kankersoort": "..." of null, "vraag_type": "..." of null, "bot_message": "..."}}

SCOPE: Als het bericht NIET over kanker, gezondheid of medische informatie gaat, zet scope op "off_topic" en antwoord dat dit buiten je expertise valt.
Bij persoonlijke medische vragen (eigen diagnose, prognose): verwijs naar de huisarts of specialist.
TOON: warm, eenvoudig, geen jargon.
Als je ai_bekendheid hebt ingevuld, antwoord dan ALLEEN met een bedankje en zeg dat je nu gaat vragen wat hun rol is. Voorbeeld: "Bedankt! Wat is uw rol? Kies hieronder een optie."
Vraag NIET tegelijk naar hun interesse of vraag. Dat komt later.
Voeg "scope": "in_scope" of "off_topic" toe aan je JSON antwoord.""",

    "rol": """Je bent een vriendelijke assistent. Je weet al dat de gebruiker {ai_bekendheid} bekend is met AI.
Je ENIGE taak nu: bepaal welke rol de gebruiker heeft.

De gebruiker zegt: "{message}"

Geldige rollen: patient, publiek, zorgverlener, student, beleidsmaker, onderzoeker, journalist, anders.
- "ik ben arts/dokter/verpleegkundige" → zorgverlener
- "ik ben patiënt/naaste/familie" → patient
- "ik ben student/docent" → student

Als de gebruiker ook een vraag stelt, vul vraag_tekst in.

Antwoord ALLEEN in JSON:
{{"gebruiker_type": "..." of null, "vraag_tekst": "..." of null, "kankersoort": "..." of null, "vraag_type": "..." of null, "bot_message": "..."}}

TOON: {tone}. Als je de rol hebt, bedank en zeg dat je nu gaat vragen waarmee je kunt helpen. Voorbeeld: "Bedankt! Waar kan ik u mee helpen?"
Geef 2-3 korte voorbeeldvragen passend bij hun rol om te inspireren.""",

    "vraag": """Je bent een vriendelijke informatie-assistent. De gebruiker is een {gebruiker_type}.
Ze zijn {ai_bekendheid} bekend met AI.

Je ENIGE taak nu: begrijp wat de gebruiker wil weten.

De gebruiker zegt: "{message}"

Analyseer de vraag:
1. Wat is de kern van hun vraag? (vraag_tekst)
2. Wordt er een specifiek type aandoening genoemd? (kankersoort — alleen als EXPLICIET genoemd)
3. Welk type informatie zoeken ze? (vraag_type: patient_info / cijfers / regionaal / onderzoek / breed)
4. Schrijf een korte samenvatting (samenvatting)

Als de vraag DUIDELIJK genoeg is om mee te zoeken:
- Vul alle velden in
- Schrijf een bot_message die ALTIJD eindigt met een ja/nee-vraag, bijvoorbeeld:
  "Als ik het goed begrijp zoekt u informatie over [samenvatting]. Klopt dit?"
  of: "Ik denk dat u dit zoekt: [samenvatting]. Zal ik hiernaar zoeken?"
  De LAATSTE zin moet ALTIJD een vraag zijn die met ja of nee beantwoord kan worden.

Als de vraag ONDUIDELIJK is of te vaag:
- Vraag door met voorbeelden passend bij het gebruikerstype
- Laat samenvatting op null

Als de vraag BUITEN SCOPE valt (niet over kanker, gezondheid of IKNL-bronnen):
- Zet scope op "off_topic"
- Antwoord: "Ik begrijp dat u informatie zoekt over [onderwerp]. Helaas valt dit buiten mijn expertise. Ik kan u helpen met vragen over kanker en aanverwante gezondheidsonderwerpen. U kunt ook contact opnemen met IKNL voor verdere hulp."
- Laat alle andere velden op null

Antwoord ALLEEN in JSON:
{{"vraag_tekst": "..." of null, "kankersoort": "..." of null, "vraag_type": "..." of null, "samenvatting": "..." of null, "scope": "in_scope" of "off_topic", "bot_message": "..."}}

TOON: {tone}. STIJL: {style}""",

    "confirm": """Je bent een informatie-assistent. Bevestig de samenvatting.

De gebruiker is een {gebruiker_type} en zoekt: {samenvatting}

De gebruiker zegt: "{message}"

Als de gebruiker bevestigt (ja, klopt, correct, etc.) → status "confirmed"
Als de gebruiker wil aanpassen → status "adjust"
Als de gebruiker een nieuwe/andere vraag stelt → status "new_question"

Antwoord ALLEEN in JSON:
{{"status": "confirmed" of "adjust" of "new_question", "vraag_tekst": "..." of null, "bot_message": "..."}}"""
}

# Tone/style per bekendheid level
TONE_MAP = {
    "niet_bekend": "Eenvoudig taalgebruik, korte zinnen, geen jargon.",
    "enigszins": "Standaard, vriendelijk, helder.",
    "erg_bekend": "Compact, direct, professioneel.",
}

STYLE_MAP = {
    "patient": "Warm en meelevend. Gebruik eenvoudige taal. Wees voorzichtig maar niet overdreven meevoelend.",
    "publiek": "Helder en informatief.",
    "zorgverlener": "Klinisch en precies. Gebruik correcte terminologie.",
    "student": "Educatief, met context.",
    "beleidsmaker": "Analytisch, cijfermatig.",
    "onderzoeker": "Wetenschappelijk, evidence-based.",
    "journalist": "Feitelijk, met bronvermelding.",
    "anders": "Neutraal en behulpzaam.",
}

# Type normalization (same as intake.py)
_TYPE_NORMALIZE = {
    "patiënt": "patient", "patiënt of naaste": "patient", "naaste": "patient",
    "arts": "zorgverlener", "dokter": "zorgverlener", "verpleegkundige": "zorgverlener",
    "wetenschapper": "onderzoeker", "onderzoeker of wetenschapper": "onderzoeker",
    "student of docent": "student", "docent": "student",
}
_VALID_TYPES = {"patient", "publiek", "zorgverlener", "student", "beleidsmaker", "onderzoeker", "journalist", "anders"}
_VALID_BEKENDHEID = {"niet_bekend", "enigszins", "erg_bekend"}


def _normalize_type(raw: str | None) -> str | None:
    if not raw:
        return None
    clean = raw.lower().strip()
    norm = _TYPE_NORMALIZE.get(clean, clean)
    return norm if norm in _VALID_TYPES else None


def _normalize_bekendheid(raw: str | None) -> str | None:
    if not raw:
        return None
    clean = raw.lower().strip()
    return clean if clean in _VALID_BEKENDHEID else None


async def _call_llm(prompt: str, model: str) -> dict:
    """Call LLM and parse JSON response."""
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
        # Strip code fences
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return json.loads(clean.strip())
    except Exception as e:
        logger.warning("LLM call failed or returned non-JSON: %s", e)
        return {"bot_message": "Kunt u dat anders formuleren?"}


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

async def bekendheid_node(state: dict) -> dict:
    prompt = STEP_PROMPTS["bekendheid"].format(
        message=state["message"].replace("{", "{{").replace("}", "}}"),
    )
    result = await _call_llm(prompt, state["model"])

    gegevens = state["gegevens"]

    if result.get("scope") == "off_topic":
        return {**state, "gegevens": gegevens, "bot_message": result.get("bot_message", ""), "off_topic": True}

    if result.get("ai_bekendheid"):
        gegevens["ai_bekendheid"] = _normalize_bekendheid(result["ai_bekendheid"]) or gegevens.get("ai_bekendheid")
    if result.get("gebruiker_type"):
        gegevens["gebruiker_type"] = _normalize_type(result["gebruiker_type"]) or gegevens.get("gebruiker_type")
    if result.get("vraag_tekst"):
        gegevens["vraag_tekst"] = result["vraag_tekst"]
    if result.get("kankersoort") and result["kankersoort"] not in ("geen", "null", ""):
        gegevens["kankersoort"] = result["kankersoort"]
    if result.get("vraag_type"):
        gegevens["vraag_type"] = result["vraag_type"]

    return {**state, "gegevens": gegevens, "bot_message": result.get("bot_message", ""), "off_topic": False}


async def rol_node(state: dict) -> dict:
    g = state["gegevens"]
    tone = TONE_MAP.get(g.get("ai_bekendheid", "enigszins"), TONE_MAP["enigszins"])
    prompt = STEP_PROMPTS["rol"].format(
        ai_bekendheid=g.get("ai_bekendheid", "enigszins"),
        message=state["message"].replace("{", "{{").replace("}", "}}"),
        tone=tone,
    )
    result = await _call_llm(prompt, state["model"])

    if result.get("scope") == "off_topic":
        return {**state, "gegevens": g, "bot_message": result.get("bot_message", ""), "off_topic": True}

    if result.get("gebruiker_type"):
        g["gebruiker_type"] = _normalize_type(result["gebruiker_type"]) or g.get("gebruiker_type")
    if result.get("vraag_tekst"):
        g["vraag_tekst"] = result["vraag_tekst"]
    if result.get("kankersoort") and result["kankersoort"] not in ("geen", "null", ""):
        g["kankersoort"] = result["kankersoort"]
    if result.get("vraag_type"):
        g["vraag_type"] = result["vraag_type"]

    return {**state, "gegevens": g, "bot_message": result.get("bot_message", ""), "off_topic": False}


async def vraag_node(state: dict) -> dict:
    g = state["gegevens"]
    tone = TONE_MAP.get(g.get("ai_bekendheid", "enigszins"), TONE_MAP["enigszins"])
    style = STYLE_MAP.get(g.get("gebruiker_type", "anders"), STYLE_MAP["anders"])
    prompt = STEP_PROMPTS["vraag"].format(
        gebruiker_type=g.get("gebruiker_type", "gebruiker"),
        ai_bekendheid=g.get("ai_bekendheid", "enigszins"),
        message=state["message"].replace("{", "{{").replace("}", "}}"),
        tone=tone,
        style=style,
    )
    result = await _call_llm(prompt, state["model"])

    # Check if off-topic
    if result.get("scope") == "off_topic":
        return {**state, "gegevens": g, "bot_message": result.get("bot_message", ""), "off_topic": True}

    if result.get("vraag_tekst"):
        g["vraag_tekst"] = result["vraag_tekst"]
    if result.get("kankersoort") and result["kankersoort"] not in ("geen", "null", ""):
        g["kankersoort"] = result["kankersoort"]
    if result.get("vraag_type"):
        g["vraag_type"] = result["vraag_type"]
    if result.get("samenvatting"):
        g["samenvatting"] = result["samenvatting"]

    return {**state, "gegevens": g, "bot_message": result.get("bot_message", ""), "off_topic": False}


async def confirm_node(state: dict) -> dict:
    g = state["gegevens"]
    prompt = STEP_PROMPTS["confirm"].format(
        gebruiker_type=g.get("gebruiker_type", "gebruiker"),
        samenvatting=g.get("samenvatting", g.get("vraag_tekst", "")),
        message=state["message"].replace("{", "{{").replace("}", "}}"),
    )
    result = await _call_llm(prompt, state["model"])

    status = result.get("status", "adjust")
    if status == "confirmed":
        g["bevestigd"] = True
    elif status == "new_question":
        if result.get("vraag_tekst"):
            g["vraag_tekst"] = result["vraag_tekst"]
            g["samenvatting"] = None
            g["bevestigd"] = False

    return {**state, "gegevens": g, "bot_message": result.get("bot_message", ""), "confirm_status": status}


# ---------------------------------------------------------------------------
# Router — decides which node to run based on current state
# ---------------------------------------------------------------------------

def route_intake(state: dict) -> str:
    """Route to the appropriate node based on what's filled in gegevens."""
    g = state["gegevens"]
    if not g.get("ai_bekendheid"):
        return "bekendheid"
    if not g.get("gebruiker_type"):
        return "rol"
    if not g.get("vraag_tekst") or not g.get("samenvatting"):
        return "vraag"
    if not g.get("bevestigd"):
        return "confirm"
    return END


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_intake_graph():
    """Build and compile the LangGraph intake flow."""
    graph = StateGraph(dict)

    graph.add_node("bekendheid", bekendheid_node)
    graph.add_node("rol", rol_node)
    graph.add_node("vraag", vraag_node)
    graph.add_node("confirm", confirm_node)

    # Entry: route to the right node based on what's missing
    graph.set_conditional_entry_point(route_intake)

    # After each node, END — one node per user message
    graph.add_edge("bekendheid", END)
    graph.add_edge("rol", END)
    graph.add_edge("vraag", END)
    graph.add_edge("confirm", END)

    return graph.compile()


# Singleton compiled graph
_graph = None


def get_intake_graph():
    global _graph
    if _graph is None:
        _graph = build_intake_graph()
    return _graph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_intake_step(
    message: str,
    gegevens: dict,
    model: str,
) -> dict:
    """Run one step of the intake graph. Returns updated gegevens + bot_message + status."""
    graph = get_intake_graph()

    state = {
        "message": message,
        "gegevens": gegevens,
        "model": model,
        "bot_message": "",
        "confirm_status": None,
    }

    # Run one step (invoke runs until END or next conditional)
    result = await graph.ainvoke(state)

    g = result["gegevens"]

    # Determine status for the frontend
    if result.get("off_topic"):
        status = "off_topic"
    elif g.get("bevestigd"):
        status = "ready_to_search"
    elif not g.get("ai_bekendheid") or not g.get("gebruiker_type") or not g.get("vraag_tekst"):
        status = "need_more_info"
    elif g.get("samenvatting"):
        status = "confirm_needed"
    else:
        status = "need_more_info"

    return {
        "gegevens": g,
        "bot_message": result.get("bot_message", ""),
        "status": status,
    }
