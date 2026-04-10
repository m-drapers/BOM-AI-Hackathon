import type { IntakeSummarizeResponse, IntakeAnalyzeResponse, GegevensModel, SSEEvent } from "./types";
import { logger } from "./logger";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";


export async function analyzeMessage(
  message: string,
  gegevens: GegevensModel,
  sessionId?: string
): Promise<IntakeAnalyzeResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/intake/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, gegevens, session_id: sessionId }),
    });
  } catch (err) {
    logger.error("intake-client", "Network error calling /api/intake/analyze", err);
    throw new Error("Network error: backend onbereikbaar");
  }
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    logger.error("intake-client", `Analyze failed: HTTP ${response.status}`, body);
    throw new Error(`Analyze failed: ${response.status}`);
  }
  return response.json();
}

function parseSSELine(line: string): { event?: string; data?: string } | null {
  if (line.startsWith("event:")) return { event: line.slice(6).trim() };
  if (line.startsWith("data:")) return { data: line.slice(5).trim() };
  return null;
}

export async function summarizeQuestion(
  gebruiker_type: string,
  vraag_tekst: string
): Promise<IntakeSummarizeResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/intake/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gebruiker_type, vraag_tekst }),
    });
  } catch (err) {
    logger.error("intake-client", "Network error calling /api/intake/summarize", err);
    throw new Error("Network error: backend onbereikbaar");
  }
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    logger.error("intake-client", `Summarize failed: HTTP ${response.status}`, body);
    throw new Error(`Summarize failed: ${response.status}`);
  }
  return response.json();
}

export async function* searchAndStream(request: {
  ai_bekendheid: string;
  gebruiker_type: string;
  vraag_tekst: string;
  kankersoort: string | null;
  vraag_type: string | null;
  samenvatting: string;
}): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/api/intake/search`, {
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
    yield { event: "error", data: { code: "NO_BODY", message: "Empty response" } };
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
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") continue;

        const parsed = parseSSELine(trimmed);
        if (!parsed) continue;

        if (parsed.event !== undefined) currentEvent = parsed.event;

        if (parsed.data !== undefined) {
          try {
            const jsonData = JSON.parse(parsed.data);
            yield { event: currentEvent as SSEEvent["event"], data: jsonData };
            if (currentEvent === "done" || currentEvent === "error") return;
          } catch {
            if (currentEvent === "token") {
              yield { event: "token", data: { text: parsed.data } };
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
