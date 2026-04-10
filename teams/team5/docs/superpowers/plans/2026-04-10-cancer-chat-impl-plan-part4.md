# Cancer Information Chat — Implementation Plan (Part 4: Frontend & Infrastructure)

> Continues from Part 3. See `2026-04-10-cancer-chat-impl-plan-part3.md` for orchestrator and API.

---

## Task 12: Frontend Project Setup

**Files:**
- Create: `frontend/package.json` (via pnpm create next-app)
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/chat-client.ts`

### Steps

- [ ] **12.1** Initialize Next.js 14 project with App Router, TypeScript, Tailwind CSS

```bash
cd teams/team5
pnpm create next-app frontend --typescript --tailwind --app --use-pnpm --no-eslint
```

Accept defaults for all prompts. This creates the scaffolding with `app/` directory, `tailwind.config.ts`, `tsconfig.json`, and `next.config.mjs`.

- [ ] **12.2** Install additional dependencies

```bash
cd teams/team5/frontend
pnpm add recharts
```

- [ ] **12.3** Create `frontend/lib/types.ts` with all TypeScript interfaces

```typescript
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
```

- [ ] **12.4** Create `frontend/lib/chat-client.ts` — SSE streaming client

```typescript
// frontend/lib/chat-client.ts

import { ChatRequest, SSEEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function parseSSELine(line: string): { event?: string; data?: string } | null {
  if (line.startsWith("event:")) {
    return { event: line.slice(6).trim() };
  }
  if (line.startsWith("data:")) {
    return { data: line.slice(5).trim() };
  }
  return null;
}

export async function* sendChatMessage(
  request: ChatRequest
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    yield {
      event: "error",
      data: {
        code: `HTTP_${response.status}`,
        message: `Server returned ${response.status}: ${response.statusText}`,
      },
    };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield {
      event: "error",
      data: { code: "NO_BODY", message: "Response body is empty" },
    };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "token";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      // Keep the last potentially incomplete line in the buffer
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") {
          // Empty line = end of SSE event block, reset for next event
          continue;
        }

        const parsed = parseSSELine(trimmed);
        if (!parsed) continue;

        if (parsed.event !== undefined) {
          currentEvent = parsed.event;
        }

        if (parsed.data !== undefined) {
          try {
            const jsonData = JSON.parse(parsed.data);
            yield {
              event: currentEvent as SSEEvent["event"],
              data: jsonData,
            };

            if (currentEvent === "done" || currentEvent === "error") {
              return;
            }
          } catch {
            // If data is not JSON, treat it as a raw token
            if (currentEvent === "token") {
              yield {
                event: "token",
                data: { text: parsed.data },
              };
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function submitFeedback(
  feedback: import("./types").FeedbackRequest
): Promise<{ id: string }> {
  const response = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feedback),
  });
  if (!response.ok) {
    throw new Error(`Feedback submission failed: ${response.status}`);
  }
  return response.json();
}
```

- [ ] **12.5** Commit

```bash
cd teams/team5
git add frontend/package.json frontend/pnpm-lock.yaml frontend/lib/types.ts frontend/lib/chat-client.ts frontend/tsconfig.json frontend/tailwind.config.ts frontend/next.config.mjs frontend/app frontend/public
git commit -m "feat(frontend): initialize Next.js 14 project with types and SSE chat client"
```

---

## Task 13: Chat Page + ChatMessage Component

**Files:**
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/components/ChatMessage.tsx`

### Steps

- [ ] **13.1** Create `frontend/app/layout.tsx` with HTML shell, Inter font, theme support, Dutch lang

```tsx
// frontend/app/layout.tsx

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "IKNL Cancer Information Chat",
  description:
    "Betrouwbare kankerinformatie uit vertrouwde bronnen — kanker.nl, NKR-Cijfers, Kankeratlas en meer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="nl" className="h-full">
      <body
        className={`${inter.className} h-full bg-gray-50 text-gray-900 antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
```

- [ ] **13.2** Create `frontend/components/ChatMessage.tsx`

```tsx
// frontend/components/ChatMessage.tsx

"use client";

import React from "react";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import SourceCard from "./SourceCard";
import DataChart from "./DataChart";
import FeedbackWidget from "./FeedbackWidget";

interface ChatMessageProps {
  message: ChatMessageType;
  sessionId: string;
  query?: string;
}

function renderMarkdown(text: string): string {
  // Lightweight markdown-to-HTML for hackathon speed
  let html = text
    // Escape HTML entities first
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // Bold
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    // Links [text](url)
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline hover:text-blue-800">$1</a>'
    )
    // Line breaks
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>")
    // Wrap in paragraph
    ;
  html = `<p>${html}</p>`;
  // Clean up empty paragraphs
  html = html.replace(/<p><\/p>/g, "");
  return html;
}

export default function ChatMessage({
  message,
  sessionId,
  query,
}: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] ${
          isUser
            ? "bg-blue-600 text-white rounded-2xl rounded-br-md px-4 py-3"
            : "bg-white border border-gray-200 rounded-2xl rounded-bl-md px-5 py-4 shadow-sm"
        }`}
      >
        {/* Message content */}
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        ) : (
          <>
            <div
              className="text-sm leading-relaxed prose prose-sm max-w-none prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline"
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(message.content),
              }}
            />

            {/* Inline charts */}
            {message.chartData && message.chartData.length > 0 && (
              <div className="mt-3 space-y-3">
                {message.chartData.map((chart, idx) => (
                  <DataChart key={idx} chartData={chart} />
                ))}
              </div>
            )}

            {/* Source cards */}
            {message.sourceCards && message.sourceCards.length > 0 && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                <SourceCard sources={message.sourceCards} />
              </div>
            )}

            {/* Feedback widget */}
            {message.id && (
              <div className="mt-2 border-t border-gray-100 pt-2">
                <FeedbackWidget
                  sessionId={sessionId}
                  messageId={message.id}
                  query={query || ""}
                  sourcesTried={
                    message.sourceCards?.map((s) => s.source) || []
                  }
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **13.3** Create `frontend/app/page.tsx` — the main chat page

```tsx
// frontend/app/page.tsx

"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { v4 as uuidv4 } from "crypto";
import type {
  ChatMessage as ChatMessageType,
  UserProfile,
  SourceCard,
  ChartData,
} from "@/lib/types";
import { sendChatMessage } from "@/lib/chat-client";
import ChatMessage from "@/components/ChatMessage";
import ProfileSelector from "@/components/ProfileSelector";

function generateId(): string {
  return crypto.randomUUID();
}

const WELCOME_MESSAGE: ChatMessageType = {
  role: "assistant",
  content:
    "Welkom bij de IKNL Kankerinformatie Chat! Ik help u graag met betrouwbare informatie over kanker uit vertrouwde bronnen zoals kanker.nl, NKR-Cijfers en de Kankeratlas.\n\nKies eerst uw profiel in het menu links, of stel direct uw vraag. Ik pas mijn antwoorden aan op basis van uw profiel.\n\n**Voorbeeldvragen:**\n- Wat is borstkanker en hoe wordt het behandeld?\n- Hoe vaak komt longkanker voor bij mannen?\n- Wat zijn de overlevingscijfers voor darmkanker?\n- Is er een hoger risico op kanker in mijn regio?",
  id: "welcome",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageType[]>([
    WELCOME_MESSAGE,
  ]);
  const [currentProfile, setCurrentProfile] =
    useState<UserProfile>("patient");
  const [inputText, setInputText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId] = useState(() => generateId());
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleProfileChange = (profile: UserProfile) => {
    setCurrentProfile(profile);
    const profileLabels: Record<UserProfile, string> = {
      patient: "Patient / naaste",
      professional: "Zorgprofessional",
      policymaker: "Beleidsmaker",
    };
    const notification: ChatMessageType = {
      role: "assistant",
      content: `Profiel gewijzigd naar **${profileLabels[profile]}**. Mijn antwoorden worden nu hierop aangepast.`,
      id: generateId(),
    };
    setMessages((prev) => [...prev, notification]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = inputText.trim();
    if (!text || isStreaming) return;

    const userMessage: ChatMessageType = {
      role: "user",
      content: text,
      id: generateId(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputText("");
    setIsStreaming(true);

    // Build history from existing messages (exclude welcome and notifications without sourceCards)
    const history = messages
      .filter((m) => m.id !== "welcome")
      .map((m) => ({ role: m.role, content: m.content }));

    const assistantMessageId = generateId();
    const assistantMessage: ChatMessageType = {
      role: "assistant",
      content: "",
      id: assistantMessageId,
      sourceCards: [],
      chartData: [],
    };

    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const stream = sendChatMessage({
        message: text,
        session_id: sessionId,
        profile: currentProfile,
        history,
      });

      for await (const event of stream) {
        switch (event.event) {
          case "token": {
            const tokenText = (event.data as { text: string }).text;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? { ...m, content: m.content + tokenText }
                  : m
              )
            );
            break;
          }
          case "source_card": {
            const card = event.data as unknown as SourceCard;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      sourceCards: [...(m.sourceCards || []), card],
                    }
                  : m
              )
            );
            break;
          }
          case "chart_data": {
            const chart = event.data as unknown as ChartData;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      chartData: [...(m.chartData || []), chart],
                    }
                  : m
              )
            );
            break;
          }
          case "done":
            // Stream complete
            break;
          case "error": {
            const errMsg = (event.data as { message: string }).message;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      content:
                        m.content +
                        `\n\nEr is een fout opgetreden: ${errMsg}`,
                    }
                  : m
              )
            );
            break;
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                content:
                  "Er is een verbindingsfout opgetreden. Probeer het opnieuw.",
              }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? "w-72" : "w-0"
        } transition-all duration-300 overflow-hidden bg-white border-r border-gray-200 flex flex-col`}
      >
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-sm font-bold">IK</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-900">
                IKNL KankerChat
              </h1>
              <p className="text-xs text-gray-500">
                Betrouwbare kankerinformatie
              </p>
            </div>
          </div>
        </div>

        <div className="p-4 flex-1">
          <ProfileSelector
            currentProfile={currentProfile}
            onProfileChange={handleProfileChange}
          />
        </div>

        <div className="p-4 border-t border-gray-200">
          <p className="text-xs text-gray-400 leading-relaxed">
            Deze chat is een prototype en geeft geen persoonlijk medisch
            advies. Raadpleeg altijd uw arts of specialist.
          </p>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 shrink-0">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-500"
            aria-label="Toggle sidebar"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <span className="text-sm text-gray-600">
            Sessie: {sessionId.slice(0, 8)}...
          </span>
          {isStreaming && (
            <span className="ml-auto text-xs text-blue-600 flex items-center gap-1">
              <span className="w-2 h-2 bg-blue-600 rounded-full animate-pulse" />
              Antwoord wordt opgesteld...
            </span>
          )}
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-3xl mx-auto">
            {messages.map((msg, idx) => (
              <ChatMessage
                key={msg.id || idx}
                message={msg}
                sessionId={sessionId}
                query={
                  msg.role === "assistant" && idx > 0
                    ? messages
                        .slice(0, idx)
                        .filter((m) => m.role === "user")
                        .pop()?.content
                    : undefined
                }
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input area */}
        <div className="border-t border-gray-200 bg-white p-4 shrink-0">
          <form
            onSubmit={handleSubmit}
            className="max-w-3xl mx-auto flex gap-3"
          >
            <textarea
              ref={inputRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Stel uw vraag over kanker..."
              rows={1}
              disabled={isStreaming}
              className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={isStreaming || !inputText.trim()}
              className="px-5 py-3 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isStreaming ? (
                <svg
                  className="w-5 h-5 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              )}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **13.4** Commit

```bash
cd teams/team5
git add frontend/app/layout.tsx frontend/app/page.tsx frontend/components/ChatMessage.tsx
git commit -m "feat(frontend): add chat page with streaming messages and layout"
```

---

## Task 14: SourceCard + DataChart + FeedbackWidget + ProfileSelector Components

**Files:**
- Create: `frontend/components/SourceCard.tsx`
- Create: `frontend/components/DataChart.tsx`
- Create: `frontend/components/FeedbackWidget.tsx`
- Create: `frontend/components/ProfileSelector.tsx`

### Steps

- [ ] **14.1** Create `frontend/components/SourceCard.tsx`

```tsx
// frontend/components/SourceCard.tsx

"use client";

import React, { useState } from "react";
import type { SourceCard as SourceCardType } from "@/lib/types";

interface SourceCardProps {
  sources: SourceCardType[];
}

const BADGE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  kanker_nl: {
    bg: "bg-blue-100",
    text: "text-blue-800",
    label: "Pati\u00ebnteninfo",
  },
  nkr_cijfers: {
    bg: "bg-green-100",
    text: "text-green-800",
    label: "Cijfers",
  },
  cancer_atlas: {
    bg: "bg-orange-100",
    text: "text-orange-800",
    label: "Atlas",
  },
  publications: {
    bg: "bg-purple-100",
    text: "text-purple-800",
    label: "Publicatie",
  },
  richtlijnen: {
    bg: "bg-teal-100",
    text: "text-teal-800",
    label: "Richtlijn",
  },
};

function getBadgeStyle(source: string) {
  return (
    BADGE_STYLES[source] || {
      bg: "bg-gray-100",
      text: "text-gray-800",
      label: source,
    }
  );
}

export default function SourceCard({ sources }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  const contributedCount = sources.filter((s) => s.contributed).length;
  const totalCount = sources.length;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg
          className={`w-3 h-3 transition-transform ${
            expanded ? "rotate-90" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span>
          {contributedCount} van {totalCount} bronnen geraadpleegd
        </span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {sources.map((source, idx) => {
            const badge = getBadgeStyle(source.source);
            return (
              <div
                key={idx}
                className={`flex items-start gap-3 px-3 py-2 rounded-lg ${
                  source.contributed
                    ? "bg-gray-50"
                    : "bg-gray-50 opacity-60"
                }`}
              >
                {/* Badge */}
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium shrink-0 ${
                    source.contributed
                      ? `${badge.bg} ${badge.text}`
                      : `border border-dashed border-gray-400 text-gray-500 bg-transparent`
                  }`}
                >
                  {badge.label}
                </span>

                {/* Source info */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-700 truncate">
                      {source.reliability}
                    </span>
                  </div>
                  {source.contributed ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline truncate block"
                    >
                      {source.url}
                    </a>
                  ) : (
                    <span className="text-xs text-gray-400 italic">
                      Geen resultaat
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **14.2** Create `frontend/components/DataChart.tsx`

```tsx
// frontend/components/DataChart.tsx

"use client";

import React from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { ChartData } from "@/lib/types";

interface DataChartProps {
  chartData: ChartData;
}

function ValueDisplay({ chartData }: DataChartProps) {
  const value = chartData.data[0]?.[chartData.yKey];
  const numValue = typeof value === "number" ? value : parseFloat(String(value));
  const isAboveAverage = numValue > 1;
  const isBelowAverage = numValue < 1;

  return (
    <div className="bg-gray-50 rounded-lg p-4 text-center">
      <p className="text-xs text-gray-500 mb-1">{chartData.title}</p>
      <p
        className={`text-3xl font-bold ${
          isAboveAverage
            ? "text-red-600"
            : isBelowAverage
            ? "text-green-600"
            : "text-gray-900"
        }`}
      >
        {typeof numValue === "number" && !isNaN(numValue)
          ? numValue.toFixed(2)
          : String(value)}
      </p>
      {chartData.unit && (
        <p className="text-xs text-gray-500 mt-1">{chartData.unit}</p>
      )}
      {!isNaN(numValue) && (
        <p
          className={`text-xs mt-1 ${
            isAboveAverage
              ? "text-red-500"
              : isBelowAverage
              ? "text-green-500"
              : "text-gray-500"
          }`}
        >
          {isAboveAverage
            ? "Hoger dan gemiddeld"
            : isBelowAverage
            ? "Lager dan gemiddeld"
            : "Gemiddeld"}
        </p>
      )}
    </div>
  );
}

export default function DataChart({ chartData }: DataChartProps) {
  if (chartData.type === "value") {
    return <ValueDisplay chartData={chartData} />;
  }

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <p className="text-xs font-medium text-gray-700 mb-3">
        {chartData.title}
      </p>
      <ResponsiveContainer width="100%" height={240}>
        {chartData.type === "line" ? (
          <LineChart data={chartData.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey={chartData.xKey}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
              unit={chartData.unit ? ` ${chartData.unit}` : ""}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Line
              type="monotone"
              dataKey={chartData.yKey}
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ r: 3, fill: "#2563eb" }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        ) : (
          <BarChart data={chartData.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey={chartData.xKey}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              axisLine={{ stroke: "#d1d5db" }}
              unit={chartData.unit ? ` ${chartData.unit}` : ""}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Bar
              dataKey={chartData.yKey}
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
              maxBarSize={48}
            />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **14.3** Create `frontend/components/FeedbackWidget.tsx`

```tsx
// frontend/components/FeedbackWidget.tsx

"use client";

import React, { useState } from "react";
import { submitFeedback } from "@/lib/chat-client";

interface FeedbackWidgetProps {
  sessionId: string;
  messageId: string;
  query: string;
  sourcesTried: string[];
}

export default function FeedbackWidget({
  sessionId,
  messageId,
  query,
  sourcesTried,
}: FeedbackWidgetProps) {
  const [rating, setRating] = useState<"positive" | "negative" | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleRate = async (value: "positive" | "negative") => {
    setRating(value);
    try {
      await submitFeedback({
        session_id: sessionId,
        message_id: messageId,
        rating: value,
        query,
        sources_tried: sourcesTried,
      });
    } catch {
      // Silently fail feedback — non-critical
    }
  };

  const handleCommentSubmit = async () => {
    if (!comment.trim()) return;
    setSubmitted(true);
    try {
      await submitFeedback({
        session_id: sessionId,
        message_id: messageId,
        rating: rating || "negative",
        comment: comment.trim(),
        query,
        sources_tried: sourcesTried,
      });
    } catch {
      // Silently fail
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        {/* Thumbs up */}
        <button
          onClick={() => handleRate("positive")}
          disabled={rating !== null}
          className={`p-1 rounded transition-colors ${
            rating === "positive"
              ? "text-green-600"
              : "text-gray-300 hover:text-gray-500"
          } disabled:cursor-default`}
          aria-label="Positieve feedback"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
        </button>

        {/* Thumbs down */}
        <button
          onClick={() => handleRate("negative")}
          disabled={rating !== null}
          className={`p-1 rounded transition-colors ${
            rating === "negative"
              ? "text-red-500"
              : "text-gray-300 hover:text-gray-500"
          } disabled:cursor-default`}
          aria-label="Negatieve feedback"
        >
          <svg
            className="w-4 h-4 rotate-180"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
          </svg>
        </button>

        {/* Missing info link */}
        {!showComment && !submitted && (
          <button
            onClick={() => setShowComment(true)}
            className="text-xs text-gray-400 hover:text-gray-600 ml-1 transition-colors"
          >
            Informatie mist?
          </button>
        )}

        {submitted && (
          <span className="text-xs text-green-600 ml-1">
            Bedankt voor uw feedback!
          </span>
        )}
      </div>

      {/* Comment input */}
      {showComment && !submitted && (
        <div className="flex gap-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCommentSubmit();
            }}
            placeholder="Welke informatie mist u?"
            className="flex-1 text-xs px-3 py-1.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            onClick={handleCommentSubmit}
            disabled={!comment.trim()}
            className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Verstuur
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **14.4** Create `frontend/components/ProfileSelector.tsx`

```tsx
// frontend/components/ProfileSelector.tsx

"use client";

import React from "react";
import type { UserProfile } from "@/lib/types";

interface ProfileSelectorProps {
  currentProfile: UserProfile;
  onProfileChange: (profile: UserProfile) => void;
}

const PROFILES: {
  value: UserProfile;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    value: "patient",
    label: "Patient / naaste",
    description: "Begrijpelijke uitleg in eenvoudig Nederlands",
    icon: (
      <svg
        className="w-5 h-5"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    value: "professional",
    label: "Zorgprofessional",
    description: "Klinische gegevens en richtlijnen",
    icon: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342"
        />
      </svg>
    ),
  },
  {
    value: "policymaker",
    label: "Beleidsmaker",
    description: "Regionale vergelijkingen en trends",
    icon: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
        />
      </svg>
    ),
  },
];

export default function ProfileSelector({
  currentProfile,
  onProfileChange,
}: ProfileSelectorProps) {
  return (
    <div>
      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Uw profiel
      </h2>
      <div className="space-y-2">
        {PROFILES.map((profile) => {
          const isActive = currentProfile === profile.value;
          return (
            <button
              key={profile.value}
              onClick={() => onProfileChange(profile.value)}
              className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                isActive
                  ? "bg-blue-50 border border-blue-200 text-blue-900"
                  : "bg-gray-50 border border-transparent hover:bg-gray-100 text-gray-700"
              }`}
            >
              <span
                className={`mt-0.5 shrink-0 ${
                  isActive ? "text-blue-600" : "text-gray-400"
                }`}
              >
                {profile.icon}
              </span>
              <div className="min-w-0">
                <p
                  className={`text-sm font-medium ${
                    isActive ? "text-blue-900" : "text-gray-700"
                  }`}
                >
                  {profile.label}
                </p>
                <p
                  className={`text-xs ${
                    isActive ? "text-blue-600" : "text-gray-500"
                  }`}
                >
                  {profile.description}
                </p>
              </div>
              {isActive && (
                <svg
                  className="w-4 h-4 text-blue-600 shrink-0 ml-auto mt-1"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **14.5** Commit

```bash
cd teams/team5
git add frontend/components/SourceCard.tsx frontend/components/DataChart.tsx frontend/components/FeedbackWidget.tsx frontend/components/ProfileSelector.tsx
git commit -m "feat(frontend): add SourceCard, DataChart, FeedbackWidget, ProfileSelector components"
```

---

## Task 15: Docker Compose + Environment

**Files:**
- Create: `teams/team5/.env.example`
- Create: `teams/team5/backend/Dockerfile`
- Create: `teams/team5/frontend/Dockerfile`
- Create: `teams/team5/docker-compose.yml`

### Steps

- [ ] **15.1** Create `.env.example`

```env
# teams/team5/.env.example

# Required: Anthropic API key for Claude LLM
ANTHROPIC_API_KEY=your-key-here

# LLM provider: "anthropic" (primary) or "ollama" (fallback)
LLM_PROVIDER=anthropic

# Embedding model: "multilingual-e5-large" (local) or "text-embedding-3-small" (OpenAI)
EMBEDDING_MODEL=multilingual-e5-large

# Ollama base URL (only needed if LLM_PROVIDER=ollama)
OLLAMA_BASE_URL=http://localhost:11434

# Backend URL for frontend to connect to
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **15.2** Create `backend/Dockerfile`

```dockerfile
# teams/team5/backend/Dockerfile

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy application source
COPY . .

# Create data directories
RUN mkdir -p /app/data/chromadb

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **15.3** Create `frontend/Dockerfile`

```dockerfile
# teams/team5/frontend/Dockerfile

FROM node:18-alpine

# Install pnpm
RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app

# Copy dependency files first for layer caching
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application source
COPY . .

# Build the Next.js application
RUN pnpm build

# Expose port
EXPOSE 3000

# Run the production server
CMD ["pnpm", "start"]
```

- [ ] **15.4** Create `docker-compose.yml`

```yaml
# teams/team5/docker-compose.yml

version: "3"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LLM_PROVIDER=${LLM_PROVIDER:-anthropic}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-multilingual-e5-large}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      start_period: 40s
      retries: 3
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
```

- [ ] **15.5** Commit

```bash
cd teams/team5
git add .env.example backend/Dockerfile frontend/Dockerfile docker-compose.yml
git commit -m "feat(infra): add Docker Compose setup with backend and frontend services"
```

---

## Task 16: Final Integration + README

**Files:**
- Modify: `teams/team5/README.md`

### Steps

- [ ] **16.1** Update the team README with complete project documentation

Replace the contents of `teams/team5/README.md` with:

```markdown
# IKNL KankerChat — Team 5

> BrabantHack_26 IKNL Med Tech track

## Team

| Name | Role |
|------|------|
| TBD  | TBD  |

## Problem

People increasingly turn to general AI systems for cancer information because
they are quick and easy to use, but the results are not always reliable. At
the same time, trusted cancer knowledge from IKNL is spread across different
platforms — kanker.nl, NKR-Cijfers, Cancer Atlas, richtlijnendatabase,
publications — making it harder for patients, professionals, and policymakers
to find accurate and consistent information.

## Solution

A chat-based interface that connects IKNL's distributed, trusted sources into
a unified conversational experience. The system retrieves, synthesises, and
cites information from multiple authoritative sources through a single
interface — while never fabricating or distorting medical information.

### Key Features

- **Multi-source RAG**: Queries kanker.nl, NKR-Cijfers, Cancer Atlas, and
  publications simultaneously via Claude tool-use
- **Profile-adapted responses**: Patient/naaste, Zorgprofessional, or
  Beleidsmaker — each gets a tailored tone, source priority, and detail level
- **Source provenance**: Every claim cites its source with clickable links
  and reliability badges
- **Inline data visualisation**: NKR statistics and Atlas SIR data rendered
  as charts within the chat
- **Ethical guardrails**: Declines personal medical advice, redirects to
  healthcare providers
- **Streaming**: Token-by-token SSE streaming for real-time responses

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Next.js Frontend                       │
│   Chat UI (streaming) | Source Cards | Data Viz (charts)  │
└─────────────────────────┬────────────────────────────────┘
                          │ SSE / streaming
┌─────────────────────────┴────────────────────────────────┐
│                 FastAPI Backend                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │             Chat Orchestrator                     │    │
│  │  Claude native tool-use + LiteLLM abstraction     │    │
│  └───────┬──────────┬──────────┬──────────┬─────────┘    │
│          │          │          │          │               │
│  ┌───────┴──┐ ┌─────┴───┐ ┌───┴───┐ ┌───┴──────────┐   │
│  │kanker.nl │ │NKR-Cijf.│ │ Atlas │ │Publications  │   │
│  │ Vector   │ │  API    │ │  API  │ │ PDF/Text     │   │
│  │ Search   │ │Connector│ │ Conn. │ │ Search       │   │
│  └───────┬──┘ └─────────┘ └───────┘ └──────────────┘   │
│          │                                               │
│  ┌───────┴─────────────┐                                 │
│  │  ChromaDB (vector)  │                                 │
│  └─────────────────────┘                                 │
└──────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.11+, async |
| LLM | Claude (Anthropic) via LiteLLM, Ollama fallback |
| Orchestration | Claude native tool-use (no framework) |
| Vector store | ChromaDB (file-based) |
| Embeddings | multilingual-e5-large (local) |
| Dev tooling | uv, pnpm, Docker Compose |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm 9+
- An Anthropic API key

### Option 1: Docker Compose (recommended)

```bash
cd teams/team5

# Set your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# Start everything
docker compose up --build
```

Open http://localhost:3000 in your browser.

### Option 2: Local Development

**Backend:**

```bash
cd teams/team5/backend
pip install uv
uv sync
uv run uvicorn main:app --reload --port 8000
```

**Frontend (separate terminal):**

```bash
cd teams/team5/frontend
pnpm install
pnpm dev
```

Open http://localhost:3000 in your browser.

### Data Ingestion

On first run, the backend will check if ChromaDB collections exist.
If not, it automatically ingests:

1. kanker.nl content from `data/kanker_nl_pages_all.json` (~2,816 pages)
2. Publications from `data/publications/` (5 PDF documents)

This takes 5-10 minutes on first startup.

## Demo Instructions

1. Start the application (Docker Compose or local dev)
2. Open http://localhost:3000
3. Select a profile in the left sidebar (Patient, Zorgprofessional, or Beleidsmaker)
4. Try these example questions:

   **As Patient/naaste:**
   - "Wat is borstkanker?"
   - "Welke behandelingen zijn er voor longkanker?"
   - "Wat zijn de bijwerkingen van chemotherapie?"

   **As Zorgprofessional:**
   - "Wat zijn de overlevingscijfers voor colorectaal carcinoom stadium III?"
   - "Hoe is de stadiumverdeling van melanoom veranderd over de afgelopen 10 jaar?"

   **As Beleidsmaker:**
   - "Hoe verschilt de incidentie van longkanker per regio?"
   - "Wat zijn de trends in borstkankerincidentie de afgelopen 20 jaar?"

5. Observe:
   - Streaming responses in real-time
   - Source cards showing which IKNL sources were consulted
   - Inline charts for statistical data
   - Profile-adapted tone and detail level

## Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| kanker.nl | ChromaDB vector search | Patient-facing cancer information (2,816 pages) |
| NKR-Cijfers | REST API | Cancer registry statistics (incidence, survival, staging) |
| Cancer Atlas | REST API | Regional cancer data (SIRs by postcode) |
| Publications | ChromaDB vector search | Research papers and IKNL reports |
| Richtlijnendatabase | ChromaDB vector search | Clinical guidelines (stretch goal) |

## Project Structure

```
teams/team5/
├── backend/
│   ├── main.py                 # FastAPI app + SSE endpoint
│   ├── orchestrator.py         # Chat orchestrator with Claude tool-use
│   ├── connectors/             # Data source connectors
│   │   ├── base.py             # SourceConnector interface
│   │   ├── kanker_nl.py        # kanker.nl vector search
│   │   ├── nkr_cijfers.py      # NKR-Cijfers API
│   │   ├── cancer_atlas.py     # Cancer Atlas API
│   │   └── publications.py     # Publications vector search
│   ├── ingestion/              # One-time data ingestion pipeline
│   ├── models.py               # Pydantic models
│   └── config.py               # Configuration
├── frontend/
│   ├── app/page.tsx            # Main chat page
│   ├── components/             # React components
│   │   ├── ChatMessage.tsx     # Message bubbles with markdown
│   │   ├── SourceCard.tsx      # Collapsible source citations
│   │   ├── DataChart.tsx       # Recharts wrapper
│   │   ├── FeedbackWidget.tsx  # Thumbs up/down + feedback
│   │   └── ProfileSelector.tsx # Profile switcher
│   └── lib/
│       ├── types.ts            # TypeScript interfaces
│       └── chat-client.ts      # SSE streaming client
├── data/                       # Shared data directory
├── docker-compose.yml
└── .env.example
```

## Documentation

- [PRD](docs/60-prd/PRD-CANCER-CHAT-001.md) — Product requirements and user stories
- [TSD](docs/61-tsd/TSD-CANCER-CHAT-001.md) — Technical design specification
- [Success Criteria](docs/success-criteria.md) — Hackathon judging criteria mapping
- [Design Specs](docs/superpowers/specs/) — Architecture and component design
```

- [ ] **16.2** Run full stack locally and verify end-to-end

```bash
# Terminal 1: Backend
cd teams/team5/backend
uv run uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd teams/team5/frontend
pnpm dev

# Terminal 3: Verify
curl -s http://localhost:8000/api/health | python -m json.tool
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"Wat is borstkanker?","session_id":"test-123","profile":"patient","history":[]}'
```

Verify:
- Backend health check returns `{"status":"healthy"}`
- SSE stream returns `token` events with Dutch text
- `source_card` events include kanker.nl URLs
- Frontend renders messages, source cards, and charts
- Profile switching works and changes response tone
- Feedback widget sends POST to `/api/feedback`

- [ ] **16.3** Final commit

```bash
cd teams/team5
git add README.md
git commit -m "docs: update README with full project documentation and demo instructions"
```

---

## Summary

| Task | Description | Files | Estimated Time |
|------|-------------|-------|----------------|
| 12 | Frontend project setup | `package.json`, `lib/types.ts`, `lib/chat-client.ts` | 30 min |
| 13 | Chat page + ChatMessage | `layout.tsx`, `page.tsx`, `ChatMessage.tsx` | 60 min |
| 14 | UI components | `SourceCard.tsx`, `DataChart.tsx`, `FeedbackWidget.tsx`, `ProfileSelector.tsx` | 60 min |
| 15 | Docker Compose + env | `docker-compose.yml`, `.env.example`, 2 Dockerfiles | 30 min |
| 16 | Integration + README | `README.md`, verification | 30 min |

**Total estimated: ~3.5 hours**

### Dependencies

- Task 12 must complete before Tasks 13 and 14
- Task 13 must complete before Task 14 (ChatMessage imports SourceCard, DataChart, FeedbackWidget)
- Tasks 12-14 must complete before Task 15 (Docker needs built frontend)
- All tasks must complete before Task 16

### Key Design Decisions

1. **No external Markdown library** — lightweight regex-based renderer avoids extra dependency for hackathon speed
2. **`crypto.randomUUID()`** — uses browser native UUID generation, no external library needed
3. **Single `page.tsx` manages all state** — avoids over-engineering with state management libraries
4. **Tailwind-only styling** — no custom CSS files, responsive by default
5. **SSE via fetch + ReadableStream** — no EventSource polyfill needed, handles all event types including structured JSON
6. **Feedback is fire-and-forget** — non-critical path, silent failure to avoid disrupting the chat experience
