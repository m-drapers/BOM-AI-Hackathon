# Intake Flow + Gegevensmodel — Design Spec

## Overview

Redesign the IKNL Infobot from free-form chat to a structured **intake → validate → search** flow. The user answers a few guided questions, the system confirms understanding, then returns targeted source links with minimal medical interpretation.

Based on the team's Userflow.md document.

---

## Gegevensmodel

```python
class GegevensModel(BaseModel):
    ai_bekendheid: Literal["niet_bekend", "enigszins", "erg_bekend"] | None = None
    gebruiker_type: Literal[
        "patient", "publiek", "zorgverlener", "student",
        "beleidsmaker", "onderzoeker", "journalist", "anders"
    ] | None = None
    vraag_tekst: str | None = None
    kankersoort: str | None = None       # only if explicitly mentioned by user
    vraag_type: str | None = None        # patient_info | cijfers | regionaal | onderzoek | breed
    samenvatting: str | None = None      # AI-generated summary for validation
    bevestigd: bool = False              # user confirmed the summary
```

No stage, region, or personal medical details. `kankersoort` is extracted only when the user literally mentions a cancer type — the system never proactively asks about cancer type.

**User-driven depth principle:** Epidemiological data (statistics, trends, regional variation) is only shown when the user's question explicitly asks for it. If someone asks "wat is longkanker?", they get kanker.nl patient info only. If they ask "hoe vaak komt longkanker voor?", NKR-Cijfers results are included. The system follows the user's lead, never upsells data sources.

---

## Flow States

```
┌─────────────────┐
│  INTAKE_START    │
│  ai_bekendheid   │ ← 3 buttons
└────────┬────────┘
         ▼
┌─────────────────┐
│  GEBRUIKER_TYPE  │ ← 8 buttons
└────────┬────────┘
         ▼
┌─────────────────┐
│  VRAAG           │ ← free text input
│  (simpler prompt │   (if niet_bekend: "Schrijf in één zin
│   if niet_bekend)│    duidelijk je vraag op.")
└────────┬────────┘
         ▼
┌─────────────────┐
│  SAMENVATTING    │ ← LLM generates summary + extracts kankersoort
│  "Klopt dit?"    │ ← Ja / Nee buttons
└────┬────────┬───┘
     │ Ja     │ Nee
     ▼        ▼
┌────────┐  ┌──────────────┐
│ SEARCH │  │ Back to       │
│        │  │ GEBRUIKER_TYPE│
└───┬────┘  └──────────────┘
    ▼
┌─────────────────┐
│  RESULTS         │ ← max 5 source links with descriptions
│  "Meer info of   │
│   nieuw onderwerp│
│   ?"             │
└────┬────────┬───┘
     │ more   │ new topic
     ▼        ▼
  broader   reset vraag_tekst + kankersoort
  search    keep gebruiker_type + ai_bekendheid
```

---

## Intake Phase (Frontend State Machine)

The intake is a **deterministic state machine in the frontend**. No LLM calls needed — just button clicks and one text input.

### State: INTAKE_START

Display: "Hoe bekend bent u met het gebruiken van een AI-chatbot?"

Buttons:
- Niet bekend
- Enigszins bekend
- Erg bekend

→ Sets `ai_bekendheid`, advances to GEBRUIKER_TYPE

### State: GEBRUIKER_TYPE

Display: "Waaronder valt u?"

Buttons:
1. Ik ben patiënt of naaste
2. Ik ben algemeen publiek
3. Ik ben een zorgverlener
4. Ik ben een student of docent
5. Ik ben een beleidsmaker
6. Ik ben een onderzoeker of wetenschapper
7. Ik ben een journalist
8. Anders

→ Sets `gebruiker_type`, advances to VRAAG

### State: VRAAG

Display depends on `ai_bekendheid`:
- niet_bekend: "Schrijf in één zin duidelijk uw vraag op."
- enigszins/erg_bekend: "Wat is uw vraag?"

→ Sets `vraag_tekst`, triggers LLM summarization, advances to SAMENVATTING

### State: SAMENVATTING

One LLM call to:
1. Generate a natural-language summary of the understood request
2. Extract `kankersoort` if explicitly mentioned (no guessing)

Display:
> "Als ik het goed begrijp is dit uw vraag:
> U bent een [gebruiker_type] en zoekt informatie over [samenvatting]. Klopt dit?"

Buttons: "Ja, dit klopt" / "Nee, ik wil iets aanpassen"
- Ja → `bevestigd = true`, advance to SEARCH
- Nee → back to GEBRUIKER_TYPE (user can change type and question)

---

## Summarize Phase (LLM)

Single LLM call with this prompt:

```
Je bent een intake-assistent. De gebruiker heeft de volgende informatie gegeven:
- Type gebruiker: {gebruiker_type}
- Vraag: {vraag_tekst}

Doe drie dingen:
1. Schrijf een korte, natuurlijke samenvatting van wat de gebruiker zoekt (max 2 zinnen).
2. Als de gebruiker een specifiek type kanker noemt, geef die naam terug als "kankersoort". Zo niet, antwoord "geen". Vraag NOOIT zelf naar een kankersoort.
3. Classificeer welk type informatie de gebruiker zoekt als "vraag_type". Kies uit:
   - "patient_info" — algemene informatie, symptomen, behandeling, leven met kanker
   - "cijfers" — statistieken, incidentie, overleving, prevalentie
   - "regionaal" — regionale verschillen, gebiedsvergelijking
   - "onderzoek" — wetenschappelijke publicaties, rapporten, studies
   - "breed" — combinatie of onduidelijk

Antwoord in JSON:
{"samenvatting": "...", "kankersoort": "..." of "geen", "vraag_type": "..."}
```

This is the only LLM call in the intake. No medical interpretation.

---

## Search Phase

When `bevestigd = true`, query connectors:

### Source priority by gebruiker_type

| Type | Priority 1 | Priority 2 | Priority 3 |
|------|-----------|-----------|-----------|
| patient, publiek | kanker.nl | NKR-Cijfers (simplified) | publications |
| zorgverlener | NKR-Cijfers + publications | kanker.nl | Cancer Atlas |
| student, onderzoeker | publications | NKR-Cijfers | kanker.nl |
| beleidsmaker | Cancer Atlas + NKR trends | publications | kanker.nl |
| journalist | kanker.nl + NKR-Cijfers | Cancer Atlas | publications |
| anders | balanced across all | - | - |

### Search execution

1. **Match question intent first** — if the question asks about statistics/cijfers, include NKR-Cijfers. If it asks about regional differences, include Cancer Atlas. If it asks about treatment/symptoms, include kanker.nl. Only include sources relevant to what was asked.
2. Use the priority table as a **tiebreaker** when multiple sources are equally relevant, not as a forced ordering.
3. Query matched connectors with `vraag_tekst` (+ `kankersoort` filter if present)
4. If fewer than 5 results from matched connectors, expand to priority-2
5. Deduplicate and rank by relevance
6. Return top 5 results

### Response format

LLM formats the results using this prompt:

```
Je bent een informatieassistent. De gebruiker is een {gebruiker_type} en zoekt: {samenvatting}.

Hieronder staan de gevonden bronnen. Maak een antwoord in dit formaat:
1. Herhaal kort de vraag van de gebruiker
2. Noem maximaal 5 bronnen met voor elke bron:
   - De naam en URL
   - Eén zin over wat daar te vinden is met betrekking tot de vraag
3. Sluit af met: "Zoekt u meer informatie of heeft u een nieuwe vraag?"

BELANGRIJK: Vat geen medische inhoud samen. Verwijs alleen naar de bron.
Pas je taalgebruik aan op basis van de bekendheid: {ai_bekendheid}
```

### Guidance level

| ai_bekendheid | Response style |
|---------------|---------------|
| niet_bekend | Eenvoudig taalgebruik, uitleg wat elke bron is, stap-voor-stap |
| enigszins | Standaard, beknopte bronbeschrijvingen |
| erg_bekend | Compact, geen uitleg, snelle weergave |

---

## Follow-up Loop

After results are shown:
- "Meer informatie" → same gegevensmodel, query next-priority connectors or broader search
- "Nieuw onderwerp" → reset `vraag_tekst`, `kankersoort`, `samenvatting`, `bevestigd` — keep `gebruiker_type` and `ai_bekendheid`
- User can also type a follow-up question directly → treated as new `vraag_tekst`

---

## Architecture Changes

### What changes from current implementation

| Component | Current | New |
|-----------|---------|-----|
| Frontend page.tsx | Free-form chat | State machine with intake steps + results display |
| Orchestrator | Claude tool-use loop | Two focused LLM calls (summarize + format results) |
| System prompts | 3 profile prompts with guardrails | Intake prompt + results formatting prompt |
| Claude tools | 6 registered tools | Same connectors, but called by orchestrator logic, not Claude |
| GegevensModel | Not present | New Pydantic model driving the flow |

### What stays the same

- All 4 connectors (kanker_nl, nkr_cijfers, cancer_atlas, publications)
- ChromaDB vector store
- FastAPI SSE streaming
- Frontend components (SourceCard, DataChart, FeedbackWidget)
- Docker, Caddy, security setup

### New/modified files

- `backend/models.py` — add GegevensModel
- `backend/orchestrator.py` — replace tool-use loop with intake+search orchestration
- `backend/main.py` — update chat endpoint to handle state transitions
- `frontend/app/page.tsx` — rewrite as state machine with intake steps
- `frontend/components/IntakeButtons.tsx` — new component for button choices
- `frontend/components/ResultsList.tsx` — new component for source results display

---

## Guardrails (unchanged)

- Only IKNL trusted sources
- Source provenance on every result (URL + name)
- No medical summarization — point to sources, don't interpret
- Decline when no sources found, redirect to kanker.nl or huisarts
- Ethical filter: redirect personal medical questions to huisarts
