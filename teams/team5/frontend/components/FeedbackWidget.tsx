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
