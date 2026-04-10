"use client";

import React, { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface SessionSummary {
  session_id: string;
  gegevens: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface SessionDetail {
  session_id: string;
  gegevens: Record<string, unknown>;
  messages: { role: string; content: string }[];
  created_at: string;
  updated_at: string;
}

export default function AdminPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [feedbackCsv, setFeedbackCsv] = useState<string | null>(null);
  const [tab, setTab] = useState<"sessions" | "feedback">("sessions");

  useEffect(() => {
    fetch(`${API_BASE}/api/admin/sessions`)
      .then((r) => r.json())
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  const loadSession = async (id: string) => {
    const r = await fetch(`${API_BASE}/api/admin/sessions/${id}`);
    if (r.ok) setSelected(await r.json());
  };

  const loadFeedback = async () => {
    const r = await fetch(`${API_BASE}/api/feedback/export`);
    if (r.ok) setFeedbackCsv(await r.text());
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          IKNL Infobot — Admin
        </h1>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <button
            type="button"
            onClick={() => setTab("sessions")}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              tab === "sessions"
                ? "bg-teal-700 text-white"
                : "bg-white text-gray-600 border"
            }`}
          >
            Sessies ({sessions.length})
          </button>
          <button
            type="button"
            onClick={() => {
              setTab("feedback");
              if (!feedbackCsv) loadFeedback();
            }}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              tab === "feedback"
                ? "bg-teal-700 text-white"
                : "bg-white text-gray-600 border"
            }`}
          >
            Feedback
          </button>
        </div>

        {tab === "sessions" && (
          <div className="grid grid-cols-3 gap-6">
            {/* Session list */}
            <div className="col-span-1 bg-white rounded-xl border p-4 max-h-[80vh] overflow-y-auto">
              <h2 className="text-sm font-semibold text-gray-700 mb-3">
                Recente sessies
              </h2>
              {sessions.length === 0 && (
                <p className="text-xs text-gray-400">Geen sessies gevonden.</p>
              )}
              <div className="space-y-2">
                {sessions.map((s) => {
                  const g = s.gegevens as Record<string, string | null>;
                  return (
                    <button
                      type="button"
                      key={s.session_id}
                      onClick={() => loadSession(s.session_id)}
                      className={`w-full text-left p-3 rounded-lg border text-xs transition-colors ${
                        selected?.session_id === s.session_id
                          ? "bg-teal-50 border-teal-300"
                          : "bg-gray-50 border-gray-200 hover:bg-gray-100"
                      }`}
                    >
                      <p className="font-mono text-gray-500">
                        {s.session_id.slice(0, 8)}...
                      </p>
                      <p className="text-gray-700 mt-1">
                        {g.gebruiker_type || "?"} — {g.vraag_tekst?.toString().slice(0, 40) || "geen vraag"}
                      </p>
                      <p className="text-gray-400 mt-0.5">
                        {new Date(s.updated_at).toLocaleString("nl-NL")}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Session detail */}
            <div className="col-span-2 bg-white rounded-xl border p-6 max-h-[80vh] overflow-y-auto">
              {selected ? (
                <>
                  <h2 className="text-sm font-semibold text-gray-700 mb-4">
                    Sessie: {selected.session_id.slice(0, 12)}...
                  </h2>

                  {/* Gegevensmodel */}
                  <div className="bg-gray-50 rounded-lg p-4 mb-4">
                    <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                      Gegevensmodel
                    </h3>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(selected.gegevens).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-gray-500">{k}: </span>
                          <span className="text-gray-900 font-medium">
                            {v === null ? "—" : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Conversation */}
                  <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                    Gesprek
                  </h3>
                  <div className="space-y-3">
                    {selected.messages.map((m, i) => (
                      <div
                        key={i}
                        className={`p-3 rounded-lg text-sm ${
                          m.role === "user"
                            ? "bg-teal-50 text-teal-900 ml-8"
                            : "bg-gray-50 text-gray-800 mr-8"
                        }`}
                      >
                        <span className="text-xs font-medium text-gray-500 block mb-1">
                          {m.role === "user" ? "Gebruiker" : "Bot"}
                        </span>
                        {m.content}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-gray-400 text-sm">
                  Selecteer een sessie om details te bekijken.
                </p>
              )}
            </div>
          </div>
        )}

        {tab === "feedback" && (
          <div className="bg-white rounded-xl border p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Feedback export (CSV)
            </h2>
            {feedbackCsv ? (
              <>
                <pre className="bg-gray-50 rounded-lg p-4 text-xs overflow-x-auto max-h-[60vh]">
                  {feedbackCsv}
                </pre>
                <a
                  href={`data:text/csv;charset=utf-8,${encodeURIComponent(feedbackCsv)}`}
                  download="feedback-export.csv"
                  className="inline-block mt-4 px-4 py-2 bg-teal-700 text-white text-sm rounded-lg hover:bg-teal-800"
                >
                  Download CSV
                </a>
              </>
            ) : (
              <p className="text-gray-400 text-sm">Laden...</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
