"use client";

import React from "react";

interface ButtonOption {
  value: string;
  label: string;
}

interface IntakeButtonsProps {
  options: ButtonOption[];
  onSelect: (value: string) => void;
  columns?: 1 | 2;
}

export default function IntakeButtons({
  options,
  onSelect,
  columns = 1,
}: IntakeButtonsProps) {
  return (
    <div
      className={`grid gap-2 ${
        columns === 2 ? "grid-cols-2" : "grid-cols-1"
      } max-w-md`}
    >
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          onClick={() => onSelect(option.value)}
          className="px-4 py-3 text-left text-sm font-medium rounded-xl border border-gray-200 bg-white text-gray-700 hover:bg-teal-50 hover:border-teal-300 hover:text-teal-800 transition-colors"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
