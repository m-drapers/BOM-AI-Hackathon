# AGENTS.md — Guidelines for AI agents working on this project

## Tone & Sensitivity

This is a **medical information** project about cancer. Users include patients, their families, and people in distressing situations. All AI-generated text — prompts, UI labels, bot messages — must follow these rules:

### DO NOT
- Use clinical/harsh terms in the UI (e.g., "kankersoort", "tumor type", "ziektebeeld")
- Ask users directly about their cancer type or diagnosis
- Use language that could cause distress or feel like an interrogation
- Show raw medical classification labels to users (keep in backend only)
- Use jargon in sidebar labels or navigation

### DO
- Use soft, empathetic language ("onderwerp", "uw vraag", "uw situatie")
- Let the user volunteer medical details in their own words — the system extracts what it needs
- Use the LLM to naturally understand cancer types from context, never force the user to categorize
- Keep UI labels neutral and non-medical ("Ervaring", "Uw rol", "Onderwerp", "Uw vraag")
- Follow the guidance level based on `ai_bekendheid` — simpler language for "niet_bekend" users

### Backend vs. Frontend distinction
- The `GegevensModel` field `kankersoort` is an **internal classification field** — it is extracted by the LLM from the user's free-text question
- It must NEVER appear as a UI label, sidebar item, or direct question to the user
- It is used only for backend connector routing (filtering search results by cancer type)

## Architecture conventions
- Backend: FastAPI + Pydantic, Python 3.11+
- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind
- LLM: LiteLLM (provider-agnostic), currently OpenRouter
- All user-facing text in Dutch
- No personal medical advice — redirect to huisarts/specialist
