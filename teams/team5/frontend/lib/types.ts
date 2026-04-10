// frontend/lib/types.ts

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  id?: string;
  sourceCards?: SourceCard[];
  chartData?: ChartData[];
}

export interface SourceCard {
  source: string;
  url: string;
  reliability: string;
  contributed: boolean;
}

export interface ChartData {
  type: "line" | "bar" | "value";
  title: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  unit?: string;
}

export type UserProfile = "patient" | "professional" | "policymaker";

export interface ChatRequest {
  message: string;
  session_id: string;
  profile: UserProfile;
  history: Pick<ChatMessage, "role" | "content">[];
}

export interface SSEEvent {
  event: "token" | "source_card" | "chart_data" | "done" | "error";
  data: Record<string, unknown>;
}

export interface DoneEventData {
  message_id: string;
  sources_tried: string[];
}

export interface ErrorEventData {
  code: string;
  message: string;
}

export interface FeedbackRequest {
  session_id: string;
  message_id: string;
  rating: "positive" | "negative";
  comment?: string;
  query: string;
  sources_tried: string[];
}

// Intake flow types

export type AiBekendheid = "niet_bekend" | "enigszins" | "erg_bekend";

export type GebruikerType =
  | "patient"
  | "publiek"
  | "zorgverlener"
  | "student"
  | "beleidsmaker"
  | "onderzoeker"
  | "journalist"
  | "anders";

export type IntakeState =
  | "INTAKE_START"
  | "GEBRUIKER_TYPE"
  | "VRAAG"
  | "SAMENVATTING"
  | "SEARCH"
  | "RESULTS";

export interface GegevensModel {
  ai_bekendheid: AiBekendheid | null;
  gebruiker_type: GebruikerType | null;
  vraag_tekst: string | null;
  kankersoort: string | null;
  vraag_type: string | null;
  samenvatting: string | null;
  bevestigd: boolean;
}

export interface IntakeSummarizeResponse {
  samenvatting: string;
  kankersoort: string;
  vraag_type: string;
}

export interface IntakeAnalyzeResponse {
  gegevens: GegevensModel;
  bot_message: string;
  status: "need_more_info" | "ready_to_search" | "confirm_needed" | "unclear" | "off_topic";
}
