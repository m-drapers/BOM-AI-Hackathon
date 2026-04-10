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
