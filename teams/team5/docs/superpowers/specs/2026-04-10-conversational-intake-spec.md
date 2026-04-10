# Conversational Intake — Specification

## Derived from
- `docs/Userflow.md` — the team's UX flow definition
- `docs/Voorbeeld uitwerking.md` — 3 worked conversation examples
- `docs/superpowers/specs/2026-04-10-intake-flow-design.md` — original technical design

## Problem

The original fixed-button state machine (click bekendheid → click type → type question → confirm → search) is too rigid. Users who type "Ik ben arts en zoek info over longkanker" should get results immediately — not be forced through 3 button screens first.

But the Userflow.md defines specific UX requirements that must be preserved:
1. The bot MUST know `gebruiker_type` before searching (determines language/sources)
2. The bot SHOULD know `ai_bekendheid` (determines guidance level)
3. The bot MUST confirm understanding before searching
4. Unclear questions get role-specific example questions
5. Off-topic questions get a polite redirect to IKNL/huisarts

## Solution: LLM Slot-Filling

One endpoint (`/api/intake/analyze`) handles all conversation turns. The LLM:
1. Extracts any GegevensModel fields from the message
2. Determines what's still missing
3. Asks for the next missing field OR confirms and triggers search

### GegevensModel (Pydantic → JSON)

```python
class GegevensModel(BaseModel):
    ai_bekendheid: "niet_bekend" | "enigszins" | "erg_bekend" | None
    gebruiker_type: "patient" | "publiek" | "zorgverlener" | ... | None
    vraag_tekst: str | None
    kankersoort: str | None       # extracted by LLM, not asked
    vraag_type: str | None        # patient_info | cijfers | regionaal | onderzoek | breed
    samenvatting: str | None      # LLM-generated summary
    bevestigd: bool = False
```

**Why Pydantic + JSON:** Validation at the API boundary (rejects invalid gebruiker_type values), serializes cleanly to/from frontend, matches existing FastAPI patterns.

**Why client-side state:** No server sessions needed. GegevensModel travels with each request. Backend stays stateless. Sidebar shows live fill progress.

### API Contract

```
POST /api/intake/analyze
Body: { message: string, gegevens: GegevensModel }
Response: { gegevens: GegevensModel, bot_message: string, status: "need_more_info" | "ready_to_search" | "unclear" }
```

### Conversation flows (from Voorbeeld uitwerking)

**Flow 1 — Step-by-step patient (Voorbeeld 1)**
```
User: "Niet bekend"              → gegevens.ai_bekendheid = "niet_bekend"
Bot asks: "Wat is uw rol?"       → status: need_more_info
User: "Patiënt"                  → gegevens.gebruiker_type = "patient"
Bot asks: "Schrijf duidelijk..." → status: need_more_info (with examples)
User: "Ik zit in het tweede stadium van longkanker..."
Bot: "U bent een patiënt en zoekt informatie over longkanker, klopt dit?"
                                 → status: ready_to_search
```

**Flow 2 — Expert shortcut (Voorbeeld 2)**
```
User: "Ik ben zorgverlener en zoek info over anamnesevragen bij beentumor"
Bot: "U bent een zorgverlener en zoekt... klopt dit?"
                                 → gegevens fills all at once
                                 → status: ready_to_search
```

**Flow 3 — Error handling (Voorbeeld 3)**
```
User: "Ik zoek informatie over haarkleur van kinderen"
Bot: "Hierover heb ik geen beschikbare informatie. Neem contact op met..."
                                 → status: unclear
```

### Search trigger rules

Search triggers when:
- `gebruiker_type` is filled AND `vraag_tekst` is filled
- LLM generates a confirmation summary in `bot_message`
- Frontend receives `status: "ready_to_search"` and auto-calls `/api/intake/search`

### Connector routing (from intake-flow-design spec)

| vraag_type | Primary sources |
|-----------|----------------|
| patient_info | kanker.nl, publications |
| cijfers | nkr_cijfers, kanker.nl |
| regionaal | cancer_atlas, nkr_cijfers |
| onderzoek | publications, nkr_cijfers |
| breed | all |

User type determines ordering within the relevant set.

### Error responses (from Userflow.md § Uitzonderingen)

| Situation | Bot response |
|-----------|-------------|
| Unclear question (patient) | "Ik begrijp uw vraag niet goed..." + patient example questions |
| Unclear question (professional) | Same + professional example questions |
| No info available | "Hierover heb ik geen beschikbare informatie. Neem contact op met..." |
| Off-topic (not cancer) | Polite redirect to IKNL contact page |

### Success criteria

| Metric | Target |
|--------|--------|
| Full question in 1 message → search | < 8s (analyze + search) |
| Step-by-step flow (3 turns) → search | < 15s total |
| Unclear message → helpful response | LLM returns status "unclear" with examples |
| Off-topic → redirect | LLM returns status "unclear" with IKNL redirect |
| GegevensModel correctly filled | All extractable fields populated from message |

## What's implemented

- [x] `/api/intake/analyze` endpoint with LLM slot-filling
- [x] `analyze_intake()` function with smart extraction prompt
- [x] Frontend conversational UI with live GegevensModel sidebar
- [x] Auto-search on `ready_to_search` status
- [x] "Meer informatie" / "Nieuw onderwerp" follow-up buttons
- [ ] Role-specific example questions in unclear responses (partially — LLM generates them, not from a fixed list per Userflow.md)
- [ ] "Neem contact op met IKNL" button for off-topic
- [ ] Feedback tab (exists as FeedbackWidget but not integrated in new flow)
