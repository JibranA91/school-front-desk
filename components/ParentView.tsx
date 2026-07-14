"use client";

import { useEffect, useRef, useState } from "react";
import {
  askFrontDesk,
  chips,
  fetchUpdates,
  loadingPhrases,
  markUpdatesSeen,
  resultToMessage,
  type Msg,
  type ParentUpdate,
} from "@/lib/frontDesk";

// A chat-session id that survives a page refresh but resets on a new login.
// Stored in sessionStorage (per-tab, cleared when the tab closes) keyed by user,
// and cleared on sign-out — so a refresh reuses it, a fresh login mints a new one.
const SESSION_KEY = "fd-chat-session";
function resolveSessionId(userKey: string): string {
  const gen = () =>
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  if (typeof window === "undefined") return gen(); // SSR throwaway; client re-resolves
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (p?.user === userKey && typeof p?.sid === "string") return p.sid;
    }
  } catch {
    /* storage unavailable — fall through to a fresh id */
  }
  const sid = gen();
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ user: userKey, sid }));
  } catch {
    /* ignore */
  }
  return sid;
}

export default function ParentView({ userKey = "" }: { userKey?: string }) {
  const [tab, setTab] = useState<"chat" | "updates">("chat");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [loadingPhrase, setLoadingPhrase] = useState("");
  const [openSources, setOpenSources] = useState<number[]>([]);
  const [updates, setUpdates] = useState<ParentUpdate[]>([]);
  const [unseen, setUnseen] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // The chat-session id tagged onto each question so the operator can identify
  // and scope this sitting. Survives a refresh (sessionStorage), resets on login.
  const sessionIdRef = useRef<string | null>(null);
  if (sessionIdRef.current === null) {
    sessionIdRef.current = resolveSessionId(userKey);
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, typing]);

  // While Sunny is thinking, cycle a random pre-K phrase every ~1.5s (avoiding
  // an immediate repeat) so it visibly switches during a single response.
  useEffect(() => {
    if (!typing) return;
    const pick = () =>
      setLoadingPhrase((prev) => {
        let next = prev;
        while (next === prev && loadingPhrases.length > 1)
          next = loadingPhrases[Math.floor(Math.random() * loadingPhrases.length)];
        return next;
      });
    pick();
    const iv = setInterval(pick, 1500);
    return () => clearInterval(iv);
  }, [typing]);

  // The chat itself is ephemeral — each login starts fresh, so we do NOT reload
  // the transcript. Staff answers to escalated questions live in the durable
  // Updates feed instead, which we poll (and refresh on focus) so late replies
  // surface with an unseen badge even across sessions.
  useEffect(() => {
    const load = () =>
      fetchUpdates()
        .then((r) => {
          setUpdates(r.updates);
          setUnseen(r.unseen);
        })
        .catch(() => {});
    load();
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", load);
    const poll = setInterval(load, 5000);
    return () => {
      clearInterval(poll);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", load);
    };
  }, []);

  // Opening the Updates tab marks it read (clears the badge).
  const openUpdates = () => {
    setTab("updates");
    if (unseen > 0) {
      setUnseen(0);
      markUpdatesSeen();
    }
  };

  const toggleSource = (id: number) =>
    setOpenSources((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const send = async (text: string) => {
    const t = (text || "").trim();
    if (!t) return;
    const uid = Date.now();
    setMessages((s) => [...s, { id: uid, type: "user", text: t }]);
    setChatInput("");
    setTyping(true);
    try {
      const result = await askFrontDesk(t, sessionIdRef.current ?? undefined);
      setMessages((s) => [...s, resultToMessage(uid + 1, result)]);
    } catch {
      setMessages((s) => [
        ...s,
        {
          id: uid + 1,
          type: "assistant-text",
          text:
            "Sorry — I couldn't reach the front desk just now. Please try again in a moment.",
        },
      ]);
    } finally {
      setTyping(false);
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "center" }}>
      <div
        className="fd-parent-card"
        style={{
          width: 390,
          maxWidth: "100%",
          height: 824,
          background: "#FFFFFF",
          border: "1px solid #EBEFF4",
          borderRadius: 44,
          boxShadow: "0 30px 70px -20px rgba(30,37,73,.28)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          style={{
            background: "#5463D6",
            padding: "18px 18px 16px",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 14,
              background: "#FFFFFF",
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
              boxShadow: "0 4px 12px rgba(30,37,73,.25)",
            }}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#29B9BB"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                color: "#FFFFFF",
                fontSize: "15.5px",
                fontWeight: 700,
                lineHeight: 1.2,
              }}
            >
              Sunnyside Early Learning
            </div>
            <div
              style={{
                color: "#C9CFFF",
                fontSize: 12,
                fontWeight: 500,
                marginTop: 2,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: 999,
                  background: "#3BBA6E",
                  display: "inline-block",
                }}
              />
              Answers from our team · replies in seconds
            </div>
          </div>
        </div>

        {/* Chat / Updates tabs */}
        <div
          style={{
            display: "flex",
            gap: 6,
            padding: "8px 12px",
            borderBottom: "1px solid #EBEFF4",
            background: "#FFFFFF",
          }}
        >
          {(
            [
              ["chat", "Chat"],
              ["updates", "Updates"],
            ] as const
          ).map(([key, label]) => {
            const active = tab === key;
            return (
              <button
                key={key}
                onClick={key === "updates" ? openUpdates : () => setTab("chat")}
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 7,
                  padding: "9px 12px",
                  borderRadius: 10,
                  border: "none",
                  cursor: "pointer",
                  fontSize: 14,
                  fontWeight: 700,
                  background: active ? "#EEF1FF" : "transparent",
                  color: active ? "#37458A" : "#737685",
                  transition: "all .15s",
                }}
              >
                {label}
                {key === "updates" && unseen > 0 && (
                  <span
                    style={{
                      background: "#FF5A5F",
                      color: "#FFFFFF",
                      fontSize: 11,
                      fontWeight: 800,
                      minWidth: 18,
                      height: 18,
                      padding: "0 5px",
                      borderRadius: 999,
                      display: "grid",
                      placeItems: "center",
                    }}
                  >
                    {unseen}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {tab === "updates" && <UpdatesFeed updates={updates} />}

        {tab === "chat" && (
          <>
        {/* Messages */}
        <div
          ref={scrollRef}
          className="fd-scroll"
          style={{ flex: 1, overflowY: "auto", background: "#FBFCFE" }}
        >
          <div
            className="fd-chat-col"
            style={{
              padding: "18px 16px 8px",
              display: "flex",
              flexDirection: "column",
              gap: 14,
            }}
          >
          <div
            style={{
              alignSelf: "flex-start",
              maxWidth: "86%",
              background: "#F1F4FF",
              color: "#18181D",
              fontSize: "14.5px",
              lineHeight: 1.5,
              padding: "13px 15px",
              borderRadius: "18px 18px 18px 6px",
            }}
          >
            Hi! I&apos;m Sunny, the Sunnyside front desk. Ask me about hours,
            tuition, meals, or your little one&apos;s day — and I&apos;ll always
            point you to where the answer comes from.
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              margin: "2px 0 4px",
            }}
          >
            {chips.map((c) => (
              <button
                key={c.label}
                className="fd-chip"
                onClick={() => send(c.q)}
                style={{
                  padding: "10px 15px",
                  borderRadius: 999,
                  border: "1.5px solid #DCE1FF",
                  background: "#FFFFFF",
                  color: "#5463D6",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all .15s",
                }}
              >
                {c.label}
              </button>
            ))}
          </div>

          {messages.map((m) => {
            if (m.type === "user") {
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-end",
                    maxWidth: "82%",
                    background: "#5463D6",
                    color: "#FFFFFF",
                    fontSize: "14.5px",
                    lineHeight: 1.45,
                    padding: "12px 16px",
                    borderRadius: "18px 18px 6px 18px",
                    animation: "fdUp .3s ease both",
                  }}
                >
                  {m.text}
                </div>
              );
            }

            if (m.type === "assistant-text") {
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    maxWidth: "86%",
                    background: "#F1F4FF",
                    color: "#18181D",
                    fontSize: "14.5px",
                    lineHeight: 1.5,
                    padding: "13px 15px",
                    borderRadius: "18px 18px 18px 6px",
                    animation: "fdUp .3s ease both",
                  }}
                >
                  {m.text}
                </div>
              );
            }

            if (m.type === "staff") {
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    width: "92%",
                    background: "#FFFFFF",
                    border: "1px solid #DDE7FF",
                    borderRadius: 20,
                    boxShadow: "0 10px 26px -14px rgba(84,99,214,.3)",
                    padding: 16,
                    animation: "fdUp .3s ease both",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 999,
                        background: "#29B9BB",
                        color: "#062B2B",
                        fontSize: 12,
                        fontWeight: 800,
                        display: "grid",
                        placeItems: "center",
                        flexShrink: 0,
                      }}
                    >
                      {(m.by ?? "Sunnyside")
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((w) => w[0])
                        .join("")
                        .toUpperCase()}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 700, color: "#18181D" }}>
                        {m.by ?? "Sunnyside staff"}
                      </div>
                      <div style={{ fontSize: 11.5, color: "#737685" }}>
                        Sunnyside staff
                      </div>
                    </div>
                    <span
                      style={{
                        background: "#EEF1FF",
                        color: "#4B57B8",
                        padding: "4px 10px",
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      Personal reply
                    </span>
                  </div>
                  <div
                    style={{
                      marginTop: 11,
                      fontSize: "14.5px",
                      lineHeight: 1.55,
                      color: "#18181D",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {m.text}
                  </div>
                </div>
              );
            }

            if (m.type === "confident") {
              const open = openSources.includes(m.id);
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    width: "92%",
                    background: "#FFFFFF",
                    border: "1px solid #EBEFF4",
                    borderRadius: 20,
                    boxShadow: "0 10px 26px -12px rgba(30,37,73,.18)",
                    padding: 16,
                    animation: "fdUp .3s ease both",
                  }}
                >
                  <div
                    style={{ fontSize: 15, lineHeight: 1.55, color: "#18181D" }}
                  >
                    {m.answer}
                  </div>
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      marginTop: 13,
                      background: "#E7F7EE",
                      color: "#227A47",
                      padding: "5px 11px",
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#3BBA6E"
                      strokeWidth="2.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
                      <path d="m9 12 2 2 4-4" />
                    </svg>
                    Grounded answer
                  </div>
                  <button
                    className="fd-source-btn"
                    onClick={() => toggleSource(m.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      width: "100%",
                      marginTop: 11,
                      background: "#F5F7FF",
                      border: "1px solid #E3E8FF",
                      color: "#5463D6",
                      padding: "10px 12px",
                      borderRadius: 12,
                      fontSize: "12.5px",
                      fontWeight: 600,
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all .15s",
                    }}
                  >
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0 }}
                    >
                      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
                    </svg>
                    <span style={{ flex: 1 }}>{m.citation}</span>
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0, opacity: 0.7 }}
                    >
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                  </button>
                  {open && (
                    <div
                      style={{
                        marginTop: 9,
                        padding: "11px 13px",
                        background: "#FBFCFE",
                        border: "1px dashed #DCE1FF",
                        borderRadius: 12,
                        fontSize: "12.5px",
                        lineHeight: 1.5,
                        color: "#5C5E6A",
                      }}
                    >
                      {m.source}
                    </div>
                  )}
                </div>
              );
            }

            if (m.type === "escalation") {
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    width: "92%",
                    background: "#FFF6EB",
                    border: "1px solid #FFE1BB",
                    borderRadius: 20,
                    boxShadow: "0 10px 26px -14px rgba(255,157,23,.35)",
                    padding: 16,
                    animation: "fdUp .3s ease both",
                  }}
                >
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 11 }}
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 12,
                        background: "#FF9D17",
                        display: "grid",
                        placeItems: "center",
                        flexShrink: 0,
                      }}
                    >
                      <svg
                        width="19"
                        height="19"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#FFFFFF"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z" />
                      </svg>
                    </div>
                    <div
                      style={{
                        fontSize: "14.5px",
                        fontWeight: 700,
                        color: "#9A5A00",
                        lineHeight: 1.25,
                      }}
                    >
                      A staff member is stepping in
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: "14.5px",
                      lineHeight: 1.55,
                      color: "#5C5E6A",
                      marginTop: 12,
                    }}
                  >
                    {m.answer}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      marginTop: 13,
                      background: "#FFFFFF",
                      border: "1px solid #FFE1BB",
                      borderRadius: 12,
                      padding: "10px 12px",
                    }}
                  >
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#C77B0E"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0 }}
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 6v6l4 2" />
                    </svg>
                    <span
                      style={{
                        fontSize: "12.5px",
                        fontWeight: 600,
                        color: "#9A5A00",
                      }}
                    >
                      A teacher will follow up with you as soon as they can.
                    </span>
                  </div>
                </div>
              );
            }

            if (m.type === "lunch") {
              const open = openSources.includes(m.id);
              return (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    width: "92%",
                    background: "#FFFFFF",
                    border: "1px solid #EBEFF4",
                    borderRadius: 20,
                    boxShadow: "0 10px 26px -12px rgba(30,37,73,.18)",
                    padding: 16,
                    animation: "fdUp .3s ease both",
                  }}
                >
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 11 }}
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 12,
                        background: "#E4F7F7",
                        display: "grid",
                        placeItems: "center",
                        flexShrink: 0,
                      }}
                    >
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#20A0A2"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M3 2v7c0 1.1.9 2 2 2h1a2 2 0 0 0 2-2V2" />
                        <path d="M7 2v20" />
                        <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7" />
                      </svg>
                    </div>
                    <div
                      style={{
                        flex: 1,
                        fontSize: "14.5px",
                        fontWeight: 700,
                        color: "#18181D",
                      }}
                    >
                      Today&apos;s lunch
                    </div>
                    <span
                      style={{
                        background: "#E4F7F7",
                        color: "#12878A",
                        padding: "4px 10px",
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      Updated today
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: "14.5px",
                      lineHeight: 1.55,
                      color: "#5C5E6A",
                      marginTop: 12,
                    }}
                  >
                    {m.answer}
                  </div>
                  <div
                    style={{
                      marginTop: 12,
                      display: "flex",
                      flexDirection: "column",
                      gap: 9,
                    }}
                  >
                    {(m.menu ?? []).map((item) => (
                      <div
                        key={item}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 11,
                          fontSize: "14.5px",
                          color: "#18181D",
                          fontWeight: 600,
                        }}
                      >
                        <span
                          style={{
                            width: 7,
                            height: 7,
                            borderRadius: 999,
                            background: "#29B9BB",
                            flexShrink: 0,
                          }}
                        />
                        {item}
                      </div>
                    ))}
                  </div>
                  <button
                    className="fd-source-btn"
                    onClick={() => toggleSource(m.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      width: "100%",
                      marginTop: 13,
                      background: "#F5F7FF",
                      border: "1px solid #E3E8FF",
                      color: "#5463D6",
                      padding: "10px 12px",
                      borderRadius: 12,
                      fontSize: "12.5px",
                      fontWeight: 600,
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all .15s",
                    }}
                  >
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0 }}
                    >
                      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
                    </svg>
                    <span style={{ flex: 1 }}>{m.citation}</span>
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0, opacity: 0.7 }}
                    >
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                  </button>
                  {open && (
                    <div
                      style={{
                        marginTop: 9,
                        padding: "11px 13px",
                        background: "#FBFCFE",
                        border: "1px dashed #DCE1FF",
                        borderRadius: 12,
                        fontSize: "12.5px",
                        lineHeight: 1.5,
                        color: "#5C5E6A",
                      }}
                    >
                      {m.source}
                    </div>
                  )}
                </div>
              );
            }

            return null;
          })}

          {typing && (
            <div
              style={{
                alignSelf: "flex-start",
                background: "#F1F4FF",
                padding: "13px 16px",
                borderRadius: "18px 18px 18px 6px",
                display: "flex",
                alignItems: "center",
                gap: 10,
                maxWidth: "86%",
              }}
            >
              <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
                {[0, 0.2, 0.4].map((d) => (
                  <span
                    key={d}
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: 999,
                      background: "#8B93C9",
                      animation: `fdBlink 1.2s infinite ${d}s`,
                    }}
                  />
                ))}
              </div>
              {loadingPhrase && (
                <span
                  key={loadingPhrase}
                  className="fd-shimmer"
                  style={{ fontSize: "13.5px", fontWeight: 600 }}
                >
                  {loadingPhrase}…
                </span>
              )}
            </div>
          )}
          </div>
        </div>

        {/* Input */}
        <div
          style={{
            padding: "12px 14px",
            borderTop: "1px solid #EBEFF4",
            background: "#FFFFFF",
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div
            className="fd-chat-col"
            style={{ display: "flex", alignItems: "center", gap: 10 }}
          >
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              background: "#F7F9FB",
              border: "1px solid #EBEFF4",
              borderRadius: 999,
              padding: "0 6px 0 16px",
            }}
          >
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  send(chatInput);
                }
              }}
              placeholder="Message Sunnyside…"
              style={{
                flex: 1,
                border: "none",
                background: "transparent",
                fontSize: "14.5px",
                color: "#18181D",
                padding: "13px 0",
                outline: "none",
              }}
            />
            <button
              className="fd-mic"
              style={{
                width: 36,
                height: 36,
                borderRadius: 999,
                border: "none",
                background: "transparent",
                color: "#737685",
                display: "grid",
                placeItems: "center",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" x2="12" y1="19" y2="22" />
              </svg>
            </button>
          </div>
          <button
            className="fd-send"
            onClick={() => send(chatInput)}
            style={{
              width: 46,
              height: 46,
              borderRadius: 999,
              border: "none",
              background: "#5463D6",
              color: "#FFFFFF",
              display: "grid",
              placeItems: "center",
              cursor: "pointer",
              flexShrink: 0,
              boxShadow: "0 6px 16px -4px rgba(84,99,214,.6)",
              transition: "background .15s",
            }}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m22 2-7 20-4-9-9-4Z" />
              <path d="M22 2 11 13" />
            </svg>
          </button>
          </div>
        </div>
          </>
        )}
      </div>
    </div>
  );
}

function UpdatesFeed({ updates }: { updates: ParentUpdate[] }) {
  if (updates.length === 0) {
    return (
      <div
        className="fd-scroll"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "40px 28px",
          textAlign: "center",
          background: "#FBFCFE",
        }}
      >
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: 16,
            background: "#EEF1FF",
            display: "grid",
            placeItems: "center",
          }}
        >
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#5463D6"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M10.268 21a2 2 0 0 0 3.464 0" />
            <path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326" />
          </svg>
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: "#18181D" }}>
          No updates yet
        </div>
        <div style={{ fontSize: "13.5px", color: "#737685", lineHeight: 1.5, maxWidth: 280 }}>
          When you ask something our staff needs to handle personally, their reply
          will show up here — even if you&apos;ve closed the app.
        </div>
      </div>
    );
  }

  return (
    <div
      className="fd-scroll"
      style={{ flex: 1, overflowY: "auto", background: "#FBFCFE" }}
    >
      <div
        className="fd-chat-col"
        style={{
          padding: "16px 16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
      {updates.map((u) => {
        const answered = u.answered;
        return (
          <div
            key={u.id}
            style={{
              background: "#FFFFFF",
              border: `1px solid ${answered ? "#DDE7FF" : "#FFE1BB"}`,
              borderRadius: 18,
              padding: 16,
              boxShadow: "0 8px 22px -16px rgba(30,37,73,.25)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 10,
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  background: answered ? "#E7F7EE" : "#FFF6EB",
                  color: answered ? "#227A47" : "#9A5A00",
                  fontSize: 11.5,
                  fontWeight: 700,
                  padding: "4px 10px",
                  borderRadius: 999,
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 999,
                    background: answered ? "#3BBA6E" : "#FF9D17",
                    display: "inline-block",
                  }}
                />
                {answered ? "Answered by staff" : "Waiting for staff"}
              </span>
              {u.unseen && (
                <span
                  style={{
                    background: "#FF5A5F",
                    color: "#FFFFFF",
                    fontSize: 10.5,
                    fontWeight: 800,
                    padding: "2px 8px",
                    borderRadius: 999,
                  }}
                >
                  New
                </span>
              )}
            </div>
            <div
              style={{
                fontSize: "13.5px",
                color: "#5C5E6A",
                lineHeight: 1.45,
              }}
            >
              <span style={{ fontWeight: 700, color: "#737685" }}>You asked: </span>
              {u.question}
            </div>
            {answered && (
              <div
                style={{
                  marginTop: 12,
                  paddingTop: 12,
                  borderTop: "1px solid #F0F2F7",
                  fontSize: "14.5px",
                  color: "#18181D",
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                }}
              >
                {u.answer}
              </div>
            )}
            {!answered && (
              <div
                style={{
                  marginTop: 10,
                  fontSize: "12.5px",
                  color: "#9A5A00",
                }}
              >
                A teacher will follow up as soon as they can.
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}
