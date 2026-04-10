"use client";

import React from "react";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import SourceCard from "@/components/SourceCard";
import DataChart from "@/components/DataChart";
import FeedbackWidget from "@/components/FeedbackWidget";

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
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-teal-700 underline hover:text-teal-900">$1</a>'
    )
    // Line breaks
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>");
  // Wrap in paragraph
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
            ? "bg-teal-700 text-white rounded-2xl rounded-br-md px-4 py-3"
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
              className="text-sm leading-relaxed prose prose-sm max-w-none prose-a:text-teal-700 prose-a:no-underline hover:prose-a:underline"
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
              <SourceCard sources={message.sourceCards} />
            )}

            {/* Feedback widget */}
            {message.id && message.id !== "welcome" && (
              <FeedbackWidget
                sessionId={sessionId}
                messageId={message.id}
                query={query || ""}
                sourcesTried={message.sourceCards?.map((s) => s.source) || []}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
