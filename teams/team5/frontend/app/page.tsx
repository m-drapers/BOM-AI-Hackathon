"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import type {
  ChatMessage as ChatMessageType,
  SourceCard,
  GegevensModel,
} from "@/lib/types";
import { analyzeMessage, searchAndStream } from "@/lib/intake-client";
import { logger } from "@/lib/logger";
import ChatMessage from "@/components/ChatMessage";
import IntakeButtons from "@/components/IntakeButtons";
import ResultsList from "@/components/ResultsList";

function generateId(): string {
  return crypto.randomUUID();
}

const INITIAL_GEGEVENS: GegevensModel = {
  ai_bekendheid: null,
  gebruiker_type: null,
  vraag_tekst: null,
  kankersoort: null,
  vraag_type: null,
  samenvatting: null,
  bevestigd: false,
};

const BEKENDHEID_OPTIONS = [
  { value: "Nee, niet eerder gebruikt", label: "Niet eerder" },
  { value: "Ja, een beetje ervaring", label: "Een beetje" },
  { value: "Ja, ik ben ervaren", label: "Ervaren" },
];

const ROL_OPTIONS = [
  { value: "Ik ben patiënt of naaste", label: "Patiënt of naaste" },
  { value: "Ik ben algemeen publiek", label: "Algemeen publiek" },
  { value: "Ik ben een zorgverlener", label: "Zorgverlener" },
  { value: "Ik ben een student of docent", label: "Student of docent" },
  { value: "Ik ben een beleidsmaker", label: "Beleidsmaker" },
  { value: "Ik ben een onderzoeker", label: "Onderzoeker" },
  { value: "Ik ben een journalist", label: "Journalist" },
  { value: "Anders", label: "Anders" },
];

const BEVESTIGING_OPTIONS = [
  { value: "Ja, dit klopt", label: "Ja, dit klopt" },
  { value: "Nee, ik wil iets aanpassen", label: "Nee, ik wil aanpassen" },
];

type FlowState = "CHAT" | "CONFIRMING" | "SEARCHING" | "RESULTS" | "OFF_TOPIC";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [gegevens, setGegevens] = useState<GegevensModel>(INITIAL_GEGEVENS);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [flowState, setFlowState] = useState<FlowState>("CHAT");
  const [currentSessionId, setCurrentSessionId] = useState("pending");

  useEffect(() => {
    setCurrentSessionId(generateId());
  }, []);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, flowState, scrollToBottom]);

  const addBotMessage = useCallback((content: string) => {
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content, id: generateId() },
    ]);
  }, []);

  const addUserMessage = useCallback((content: string) => {
    setMessages((prev) => [
      ...prev,
      { role: "user", content, id: generateId() },
    ]);
  }, []);

  // Welcome message
  useEffect(() => {
    addBotMessage(
      "Welkom bij de IKNL Infobot! Ik help u informatie te vinden uit vertrouwde bronnen.\n\n" +
        "**Let op:** Dit is een prototype (BrabantHack_26). Dit is geen medisch hulpmiddel.\n\n" +
        "**Heeft u eerder een chatbot zoals deze gebruikt?**"
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Determine which step we're on based on filled fields ---
  const currentStep = (() => {
    if (flowState === "CONFIRMING") return "BEVESTIGING";
    if (flowState === "SEARCHING") return "SEARCHING";
    if (flowState === "RESULTS") return "RESULTS";
    if (flowState === "OFF_TOPIC") return "OFF_TOPIC";
    if (!gegevens.ai_bekendheid) return "BEKENDHEID";
    if (!gegevens.gebruiker_type) return "ROL";
    if (!gegevens.vraag_tekst) return "VRAAG";
    return "VRAAG"; // has everything but not confirmed yet
  })();

  // --- Sidebar display ---
  const gegevensItems = [
    { label: "Ervaring", value: gegevens.ai_bekendheid },
    { label: "Uw rol", value: gegevens.gebruiker_type },
    { label: "Onderwerp", value: gegevens.vraag_type },
    {
      label: "Uw vraag",
      value: gegevens.vraag_tekst
        ? gegevens.vraag_tekst.length > 40
          ? gegevens.vraag_tekst.slice(0, 40) + "..."
          : gegevens.vraag_tekst
        : null,
    },
  ];
  const filledCount = gegevensItems.filter((i) => i.value).length;

  // --- Core handler ---
  const handleSend = async (text: string) => {
    if (!text.trim() || isLoading) return;
    const msg = text.trim();

    addUserMessage(msg);
    setInputText("");
    setIsLoading(true);

    try {
      const result = await analyzeMessage(msg, gegevens, currentSessionId);
      setGegevens(result.gegevens);
      addBotMessage(result.bot_message);

      if (result.status === "ready_to_search") {
        await doSearch(result.gegevens);
      } else if (result.status === "confirm_needed") {
        setFlowState("CONFIRMING");
      } else if (result.status === "off_topic") {
        setFlowState("OFF_TOPIC");
      }
    } catch (err) {
      logger.error("page", "handleSend failed", err);
      addBotMessage("Er is iets misgegaan. Probeer het opnieuw.");
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleConfirm = async (confirmed: boolean) => {
    if (confirmed) {
      addUserMessage("Ja, dit klopt");
      const confirmedGegevens = { ...gegevens, bevestigd: true };
      setGegevens(confirmedGegevens);
      await doSearch(confirmedGegevens);
    } else {
      addUserMessage("Nee, ik wil iets aanpassen");
      setGegevens((prev) => ({
        ...prev,
        vraag_tekst: null,
        samenvatting: null,
        vraag_type: null,
        bevestigd: false,
      }));
      addBotMessage("Geen probleem. Wat wilt u weten?");
      setFlowState("CHAT");
    }
  };

  const doSearch = async (g: GegevensModel) => {
    setFlowState("SEARCHING");
    setIsLoading(true);

    const resultMsgId = generateId();
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", id: resultMsgId, sourceCards: [] },
    ]);

    try {
      const stream = searchAndStream({
        ai_bekendheid: g.ai_bekendheid || "enigszins",
        gebruiker_type: g.gebruiker_type || "publiek",
        vraag_tekst: g.vraag_tekst || "",
        kankersoort: g.kankersoort,
        vraag_type: g.vraag_type,
        samenvatting: g.samenvatting || g.vraag_tekst || "",
      });

      for await (const event of stream) {
        switch (event.event) {
          case "token": {
            const tokenText = (event.data as { text: string }).text;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === resultMsgId
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
                m.id === resultMsgId
                  ? { ...m, sourceCards: [...(m.sourceCards || []), card] }
                  : m
              )
            );
            break;
          }
          case "done":
            break;
          case "error": {
            const errMsg = (event.data as { message: string }).message;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === resultMsgId
                  ? { ...m, content: m.content + `\n\nFout: ${errMsg}` }
                  : m
              )
            );
            break;
          }
        }
      }

      setFlowState("RESULTS");
    } catch (err) {
      logger.error("page", "doSearch failed", err);
      addBotMessage("Er is een verbindingsfout opgetreden. Probeer het opnieuw.");
      setFlowState("CHAT");
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewTopic = () => {
    setGegevens((prev) => ({
      ...prev,
      vraag_tekst: null,
      kankersoort: null,
      vraag_type: null,
      samenvatting: null,
      bevestigd: false,
    }));
    addBotMessage("Stel gerust een nieuwe vraag.");
    setFlowState("CHAT");
  };

  const handleMoreInfo = () => {
    addBotMessage("Ik zoek aanvullende informatie...");
    doSearch(gegevens);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(inputText);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend(inputText);
    }
  };

  // --- Which buttons to show ---
  const currentButtons = (() => {
    if (isLoading) return null;
    if (currentStep === "BEKENDHEID") return BEKENDHEID_OPTIONS;
    if (currentStep === "ROL") return ROL_OPTIONS;
    if (currentStep === "BEVESTIGING") return null; // handled separately
    return null;
  })();

  // --- Render ---
  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-72 bg-white border-r border-gray-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-teal-700 rounded-lg flex items-center justify-center">
              <span className="text-white text-sm font-bold">IK</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-900">IKNL Infobot</h1>
              <p className="text-xs text-gray-500">Informatie assistent</p>
            </div>
          </div>
        </div>

        <div className="p-4 flex-1">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
            Uw profiel ({filledCount}/{gegevensItems.length})
          </p>
          <div className="space-y-2">
            {gegevensItems.map((item) => (
              <div key={item.label} className="flex items-start gap-2">
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                    item.value ? "bg-teal-600 text-white" : "bg-gray-100 text-gray-300"
                  }`}
                >
                  {item.value ? (
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    <span className="text-[10px]">-</span>
                  )}
                </div>
                <div className="min-w-0">
                  <p className={`text-xs ${item.value ? "text-gray-700 font-medium" : "text-gray-400"}`}>
                    {item.label}
                  </p>
                  {item.value && <p className="text-xs text-teal-700 truncate">{item.value}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-gray-200">
          <p className="text-xs text-gray-400 leading-relaxed">
            Dit is een prototype en geen medisch hulpmiddel. Raadpleeg altijd uw arts of specialist.
          </p>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 shrink-0">
          <span className="text-sm text-gray-600">
            Sessie: {currentSessionId === "pending" ? "..." : currentSessionId.slice(0, 8) + "..."}
          </span>
          {isLoading && (
            <span className="ml-auto text-xs text-teal-700 flex items-center gap-1">
              <span className="w-2 h-2 bg-teal-600 rounded-full animate-pulse" />
              {flowState === "SEARCHING" ? "Bronnen worden doorzocht..." : "Wordt verwerkt..."}
            </span>
          )}
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg, idx) => (
              <ChatMessage
                key={msg.id || idx}
                message={msg}
                sessionId={currentSessionId}
                query={
                  msg.role === "assistant" && idx > 0
                    ? messages.slice(0, idx).filter((m) => m.role === "user").pop()?.content
                    : undefined
                }
              />
            ))}

            {/* Step-specific buttons */}
            {currentButtons && (
              <div className="ml-10">
                <IntakeButtons
                  options={currentButtons}
                  onSelect={(v) => handleSend(v)}
                  columns={currentStep === "ROL" ? 2 : 1}
                />
              </div>
            )}

            {/* Confirmation buttons */}
            {currentStep === "BEVESTIGING" && !isLoading && (
              <div className="ml-10">
                <IntakeButtons
                  options={BEVESTIGING_OPTIONS}
                  onSelect={(v) => handleConfirm(v === "Ja, dit klopt")}
                />
              </div>
            )}

            {/* Results follow-up */}
            {flowState === "RESULTS" && !isLoading && (
              <div className="ml-10">
                <ResultsList onMoreInfo={handleMoreInfo} onNewTopic={handleNewTopic} />
              </div>
            )}

            {/* Off-topic: redirect to IKNL or try again */}
            {flowState === "OFF_TOPIC" && !isLoading && (
              <div className="ml-10 flex gap-3">
                <a
                  href="https://www.iknl.nl/contact"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2.5 text-sm font-medium rounded-xl border border-teal-300 bg-teal-50 text-teal-800 hover:bg-teal-100 transition-colors"
                >
                  Neem contact op met IKNL
                </a>
                <button
                  type="button"
                  onClick={() => {
                    setGegevens((prev) => ({ ...prev, vraag_tekst: null, samenvatting: null, vraag_type: null }));
                    addBotMessage("Stel gerust een nieuwe vraag over kanker of gezondheid.");
                    setFlowState("CHAT");
                  }}
                  className="px-4 py-2.5 text-sm font-medium rounded-xl border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Stel opnieuw een vraag
                </button>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input area — always visible (except during confirmation) */}
        {currentStep !== "BEVESTIGING" && currentStep !== "OFF_TOPIC" && (
          <div className="border-t border-gray-200 bg-white p-4 shrink-0">
            <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex gap-3">
              <textarea
                ref={inputRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  currentStep === "BEKENDHEID"
                    ? "Of typ uw antwoord..."
                    : currentStep === "ROL"
                    ? "Kies hierboven uw rol..."
                    : currentStep === "VRAAG"
                    ? "Stel uw vraag..."
                    : "Stel een nieuwe vraag..."
                }
                rows={1}
                disabled={isLoading || currentStep === "BEKENDHEID" || currentStep === "ROL"}
                className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={isLoading || !inputText.trim()}
                className="px-5 py-3 bg-teal-700 text-white text-sm font-medium rounded-xl hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isLoading ? (
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
}
