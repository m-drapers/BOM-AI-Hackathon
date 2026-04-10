"use client";

import React from "react";

interface ResultsListProps {
  onMoreInfo: () => void;
  onNewTopic: () => void;
}

export default function ResultsList({
  onMoreInfo,
  onNewTopic,
}: ResultsListProps) {
  return (
    <div className="flex gap-3">
      <button
        type="button"
        onClick={onMoreInfo}
        className="px-4 py-2.5 text-sm font-medium rounded-xl border border-teal-300 bg-teal-50 text-teal-800 hover:bg-teal-100 transition-colors"
      >
        Meer informatie
      </button>
      <button
        type="button"
        onClick={onNewTopic}
        className="px-4 py-2.5 text-sm font-medium rounded-xl border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 transition-colors"
      >
        Nieuw onderwerp
      </button>
    </div>
  );
}
