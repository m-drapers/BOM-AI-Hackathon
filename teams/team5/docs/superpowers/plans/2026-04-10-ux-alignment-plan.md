# UX Alignment Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Align the conversational intake implementation with the UX requirements in Userflow.md and Voorbeeld uitwerking.md

**Architecture:** The `/api/intake/analyze` LLM endpoint already handles slot-filling. This plan adds the missing UX features: role-specific examples, IKNL contact button, feedback integration, and confirmation flow polish.

**What's already done:** Conversational intake works end-to-end (analyze → search → results). This plan covers the UX gaps identified in the spec.

---

### Task 1: Role-specific example questions for unclear inputs

**Files:**
- Modify: `backend/intake.py` (update `_ANALYZE_PROMPT`)

The Userflow.md specifies different example questions per role:

**Patient/naaste:**
- Hoe help ik mijn vrouw met borstkanker? Ze zit in het tweede stadium.
- Wat is het verschil tussen het eerste en tweede stadium bij botkanker?
- Wat kan ik verwachten van de behandeling van een goedaardige tumor?

**Zorgverlener:**
- Ik zoek belangrijke anamnesevragen bij radiologische verdenking op een primair maligne beentumor.
- Welke bijwerkingen van chemotherapie moet ik monitoren?
- Wat zijn de richtlijnen voor follow-up na behandeling van darmkanker?

- [ ] **Step 1:** Add these example lists to the `_ANALYZE_PROMPT` so the LLM uses them in unclear responses
- [ ] **Step 2:** Test with curl: `{"message": "xyz", "gegevens": {"gebruiker_type": "patient"}}` should return patient examples
- [ ] **Step 3:** Test: `{"message": "xyz", "gegevens": {"gebruiker_type": "zorgverlener"}}` should return professional examples
- [ ] **Step 4:** Commit

---

### Task 2: Off-topic detection with IKNL redirect

**Files:**
- Modify: `backend/intake.py` (update `_ANALYZE_PROMPT`)
- Modify: `frontend/app/page.tsx` (add IKNL contact button on unclear)

Per Userflow: "Hierover heb ik geen beschikbare informatie. Neem contact op met uw zorgverlener of IKNL."

Per Voorbeeld 3: User asks about "haarkleur van kinderen" → bot says no info, redirects.

- [ ] **Step 1:** Update `_ANALYZE_PROMPT` to distinguish "unclear" (bad phrasing) from "off_topic" (not cancer-related). Add status value `"off_topic"`.
- [ ] **Step 2:** Add `IntakeAnalyzeResponse.status` literal: `"need_more_info" | "ready_to_search" | "unclear" | "off_topic"`
- [ ] **Step 3:** In frontend, when status is "off_topic", show two buttons: "Neem contact op met IKNL" (links to https://iknl.nl/contact) and "Stel opnieuw een vraag"
- [ ] **Step 4:** Test with curl: `{"message": "Wat is de haarkleur van kinderen?", "gegevens": {"gebruiker_type": "patient"}}`
- [ ] **Step 5:** Commit

---

### Task 3: Confirmation before search (Nee path)

**Files:**
- Modify: `frontend/app/page.tsx`

Per Userflow: After the summary, user can click "Nee, ik wil iets aanpassen" and gets sent back to rephrase their question. Per updated Userflow.md line 30-31: "Nee" → back to question input (vraag 3).

Currently: `ready_to_search` auto-triggers search without explicit confirmation. The LLM generates a confirmation message but doesn't wait for "Ja/Nee".

- [ ] **Step 1:** When `status === "ready_to_search"`, DON'T auto-search. Instead show "Ja, dit klopt" / "Nee, ik wil iets aanpassen" buttons.
- [ ] **Step 2:** "Ja" → trigger `doSearch(gegevens)`
- [ ] **Step 3:** "Nee" → clear vraag_tekst/samenvatting, show text input for new question
- [ ] **Step 4:** Test full flow in browser
- [ ] **Step 5:** Commit

---

### Task 4: Feedback integration

**Files:**
- Modify: `frontend/app/page.tsx` (re-enable FeedbackWidget in results)

Per Userflow § Feedback: "Ten alle tijden is er een tabje met 'Feedback'."

The FeedbackWidget component already exists and works. It just needs to be shown in the new conversational flow.

- [ ] **Step 1:** The `ChatMessage` component already renders `FeedbackWidget` for messages with an `id`. Verify it appears on result messages.
- [ ] **Step 2:** Ensure `query` and `sourcesTried` props are passed correctly from the search results.
- [ ] **Step 3:** Test: submit feedback after getting results.
- [ ] **Step 4:** Commit

---

### Task 5: "Meer informatie" broadens search

**Files:**
- Modify: `backend/intake.py` (accept `expand` flag in search)
- Modify: `frontend/app/page.tsx`

Per Userflow: "Meer informatie" should expand to next-priority connectors or broader search.

Currently: re-runs the same search with the same gegevens.

- [ ] **Step 1:** Add optional `expand: bool = False` to `IntakeSearchRequest`
- [ ] **Step 2:** In `search_and_format`, when `expand=True`, query ALL connectors (ignore vraag_type filter), skip sources already shown
- [ ] **Step 3:** Frontend: handleMoreInfo sets expand flag
- [ ] **Step 4:** Commit

---

### Priority order for hackathon

1. **Task 3** (confirmation before search) — most visible UX gap
2. **Task 1** (role-specific examples) — quick LLM prompt change
3. **Task 2** (off-topic detection) — important for demo
4. **Task 4** (feedback) — should already work, just verify
5. **Task 5** (broader search) — nice-to-have
