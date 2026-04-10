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
