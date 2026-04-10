"""Pydantic data models for the cancer-info-chat system."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage] = []


class Citation(BaseModel):
    url: str
    title: str
    reliability: str


class SourceCard(BaseModel):
    source: str
    url: str
    reliability: str
    contributed: bool


class ChartData(BaseModel):
    type: Literal["line", "bar", "value"]
    title: str
    data: list[dict]
    x_key: str
    y_key: str
    unit: Optional[str] = None


class FeedbackEntry(BaseModel):
    session_id: str
    message_id: str
    rating: Literal["positive", "negative"]
    comment: Optional[str] = None
    query: str
    sources_tried: list[str]
    profile: Optional[str] = None
    timestamp: Optional[datetime] = None

    @model_validator(mode="after")
    def set_timestamp(self) -> "FeedbackEntry":
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        return self


class SourceResult(BaseModel):
    data: dict | list | str | None
    summary: str
    sources: list[Citation]
    visualizable: bool


class SessionContext(BaseModel):
    session_id: str
    profile: Literal["patient", "professional", "policymaker"]
    history: list[ChatMessage]
    inferred_intent: Optional[str] = None


class GegevensModel(BaseModel):
    """Intake data model — drives the structured intake flow."""
    ai_bekendheid: Literal["niet_bekend", "enigszins", "erg_bekend"] | None = None
    gebruiker_type: Literal[
        "patient", "publiek", "zorgverlener", "student",
        "beleidsmaker", "onderzoeker", "journalist", "anders"
    ] | None = None
    vraag_tekst: str | None = None
    kankersoort: str | None = None
    vraag_type: str | None = None
    samenvatting: str | None = None
    bevestigd: bool = False


class IntakeSummarizeRequest(BaseModel):
    """Request body for /api/intake/summarize."""
    gebruiker_type: Literal[
        "patient", "publiek", "zorgverlener", "student",
        "beleidsmaker", "onderzoeker", "journalist", "anders"
    ]
    vraag_tekst: str


class IntakeSummarizeResponse(BaseModel):
    """Response from /api/intake/summarize."""
    samenvatting: str
    kankersoort: str  # "geen" if not mentioned
    vraag_type: str   # patient_info | cijfers | regionaal | onderzoek | breed


class IntakeAnalyzeRequest(BaseModel):
    """Request body for /api/intake/analyze — conversational intake."""
    message: str
    session_id: str | None = None
    gegevens: GegevensModel = GegevensModel()


class IntakeAnalyzeResponse(BaseModel):
    """Response from /api/intake/analyze."""
    gegevens: GegevensModel
    bot_message: str
    status: Literal["need_more_info", "ready_to_search", "unclear"]


class IntakeSearchRequest(BaseModel):
    """Request body for /api/intake/search."""
    ai_bekendheid: Literal["niet_bekend", "enigszins", "erg_bekend"]
    gebruiker_type: Literal[
        "patient", "publiek", "zorgverlener", "student",
        "beleidsmaker", "onderzoeker", "journalist", "anders"
    ]
    vraag_tekst: str
    kankersoort: str | None = None
    vraag_type: str | None = None
    samenvatting: str
