// frontend/lib/chat-client.ts

import { ChatRequest, SSEEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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
