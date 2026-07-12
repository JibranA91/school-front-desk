"use client";

import { useState, type CSSProperties } from "react";
import {
  changelog,
  inbox,
  statusStyles,
  suggestions,
} from "@/lib/frontDesk";

type Nav = "inbox" | "knowledge" | "changelog";
type ProposalState = "idle" | "proposed" | "confirmed";

function navBtn(active: boolean): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "11px 13px",
    borderRadius: 12,
    border: "none",
    cursor: "pointer",
    width: "100%",
    textAlign: "left",
    fontFamily: "inherit",
    fontSize: 14,
    fontWeight: 600,
    background: active ? "#5463D6" : "transparent",
    color: active ? "#FFFFFF" : "#AEB4D6",
    transition: "background .15s",
  };
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function OperatorView({
  operatorName = "Maria Chen",
  operatorTitle = "Director",
}: {
  operatorName?: string;
  operatorTitle?: string;
}) {
  const [nav, setNav] = useState<Nav>("inbox");
  const [authorText, setAuthorText] = useState("");
  const [proposalState, setProposalState] = useState<ProposalState>("idle");
  const [conflictOpen, setConflictOpen] = useState(false);

  const propose = () => {
    const t = (authorText || "").toLowerCase();
    if (!t.trim()) return;
    if (t.includes("6:30") || t.includes("open at") || t.includes("opening")) {
      setConflictOpen(true);
    } else {
      setProposalState("proposed");
    }
  };

  return (
    <div
      style={{
        width: "min(1180px,96vw)",
        margin: "0 auto",
        height: "calc(100vh - 118px)",
        minHeight: 620,
        background: "#FFFFFF",
        border: "1px solid #EBEFF4",
        borderRadius: 24,
        boxShadow: "0 30px 70px -30px rgba(30,37,73,.3)",
        overflow: "hidden",
        display: "flex",
        position: "relative",
      }}
    >
      {/* Sidebar */}
      <div
        style={{
          width: 248,
          flexShrink: 0,
          background: "#1E2549",
          padding: "22px 16px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 11,
            padding: "0 6px 20px",
          }}
        >
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 11,
              background: "#5463D6",
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
            }}
          >
            <svg
              width="21"
              height="21"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#FFFFFF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          </div>
          <div>
            <div
              style={{
                color: "#FFFFFF",
                fontSize: "14.5px",
                fontWeight: 700,
                lineHeight: 1.1,
              }}
            >
              Sunnyside
            </div>
            <div
              style={{
                color: "#8188B8",
                fontSize: "11.5px",
                fontWeight: 600,
                marginTop: 2,
              }}
            >
              Front Desk · Operator
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <button
            className="fd-nav"
            onClick={() => setNav("inbox")}
            style={navBtn(nav === "inbox")}
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
              <path d="M22 12h-6l-2 3h-4l-2-3H2" />
              <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
            </svg>
            <span style={{ flex: 1 }}>Inbox</span>
            <span
              style={{
                background: "#FF9D17",
                color: "#3A2200",
                fontSize: 11,
                fontWeight: 800,
                padding: "2px 8px",
                borderRadius: 999,
              }}
            >
              2
            </span>
          </button>
          <button
            className="fd-nav"
            onClick={() => setNav("knowledge")}
            style={navBtn(nav === "knowledge")}
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
              <path d="M12 7v14" />
              <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
            </svg>
            <span style={{ flex: 1 }}>Knowledge</span>
          </button>
          <button
            className="fd-nav"
            onClick={() => setNav("changelog")}
            style={navBtn(nav === "changelog")}
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
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M12 7v5l4 2" />
            </svg>
            <span style={{ flex: 1 }}>Changelog</span>
          </button>
        </div>

        <div
          style={{
            marginTop: "auto",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 8px 0",
            borderTop: "1px solid #2D355F",
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 999,
              background: "#29B9BB",
              color: "#062B2B",
              fontSize: "12.5px",
              fontWeight: 800,
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
            }}
          >
            {initialsOf(operatorName)}
          </div>
          <div>
            <div
              style={{
                color: "#FFFFFF",
                fontSize: 13,
                fontWeight: 700,
                lineHeight: 1.1,
              }}
            >
              {operatorName}
            </div>
            <div
              style={{ color: "#8188B8", fontSize: "11.5px", marginTop: 2 }}
            >
              {operatorTitle}
            </div>
          </div>
        </div>
      </div>

      {/* Main panel */}
      <div
        className="fd-scroll"
        style={{ flex: 1, overflowY: "auto", background: "#F7F9FB" }}
      >
        {nav === "inbox" && (
          <div style={{ padding: "30px 34px" }}>
            <div
              style={{
                fontSize: 24,
                fontWeight: 800,
                color: "#18181D",
                letterSpacing: "-.01em",
              }}
            >
              Inbox
            </div>
            <div style={{ fontSize: 14, color: "#5C5E6A", marginTop: 4 }}>
              Every question parents asked — newest first. Escalations and
              low-confidence answers surface at the top.
            </div>
            <div
              style={{
                marginTop: 22,
                background: "#FFFFFF",
                border: "1px solid #EBEFF4",
                borderRadius: 16,
                overflow: "hidden",
                boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
              }}
            >
              {inbox.map((i) => {
                const s = statusStyles[i.status];
                return (
                  <div
                    key={i.q}
                    className="fd-inbox-row"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 16,
                      padding: "16px 18px",
                      borderBottom: "1px solid #F0F3F8",
                      cursor: "pointer",
                      transition: "background .12s",
                    }}
                  >
                    <span
                      style={{
                        background: s.bg,
                        color: s.color,
                        padding: "5px 11px",
                        borderRadius: 999,
                        fontSize: 12,
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                        flexShrink: 0,
                      }}
                    >
                      {s.label}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 15,
                          fontWeight: 600,
                          color: "#18181D",
                        }}
                      >
                        {i.q}
                      </div>
                      <div
                        style={{
                          fontSize: "12.5px",
                          color: "#737685",
                          marginTop: 3,
                        }}
                      >
                        {i.who} · {i.time}
                      </div>
                    </div>
                    <svg
                      width="17"
                      height="17"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#C4C8D4"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ flexShrink: 0 }}
                    >
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {nav === "knowledge" && (
          <div style={{ padding: "30px 34px", maxWidth: 760 }}>
            <div
              style={{
                fontSize: 24,
                fontWeight: 800,
                color: "#18181D",
                letterSpacing: "-.01em",
              }}
            >
              Knowledge
            </div>
            <div style={{ fontSize: 14, color: "#5C5E6A", marginTop: 4 }}>
              Teach the front desk in plain language. I&apos;ll turn it into a
              precise change and check it against what parents already see.
            </div>

            <div
              style={{
                marginTop: 22,
                background: "#FFFFFF",
                border: "1px solid #EBEFF4",
                borderRadius: 20,
                padding: 20,
                boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 9,
                  fontSize: 15,
                  fontWeight: 700,
                  color: "#18181D",
                }}
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#5463D6"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z" />
                </svg>
                Tell Sunnyside what changed
              </div>
              <textarea
                value={authorText}
                onChange={(e) => setAuthorText(e.target.value)}
                placeholder="e.g. We're now closed the Friday after Thanksgiving"
                style={{
                  width: "100%",
                  marginTop: 13,
                  background: "#F7F9FB",
                  border: "1px solid #EBEFF4",
                  borderRadius: 14,
                  padding: 14,
                  fontSize: "14.5px",
                  lineHeight: 1.5,
                  color: "#18181D",
                  minHeight: 88,
                  resize: "none",
                }}
              />
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  marginTop: 11,
                }}
              >
                {suggestions.map((sug) => (
                  <button
                    key={sug.label}
                    className="fd-chip"
                    onClick={() => setAuthorText(sug.text)}
                    style={{
                      padding: "8px 13px",
                      borderRadius: 999,
                      border: "1px solid #E3E8FF",
                      background: "#F5F7FF",
                      color: "#5463D6",
                      fontSize: "12.5px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all .15s",
                    }}
                  >
                    {sug.label}
                  </button>
                ))}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginTop: 16,
                }}
              >
                <div style={{ flex: 1, fontSize: "12.5px", color: "#737685" }}>
                  I&apos;ll draft an exact edit and flag any conflicts before
                  anything goes live.
                </div>
                <button
                  className="fd-primary"
                  onClick={propose}
                  style={{
                    background: "#5463D6",
                    color: "#FFFFFF",
                    border: "none",
                    borderRadius: 12,
                    padding: "11px 20px",
                    fontSize: 14,
                    fontWeight: 700,
                    cursor: "pointer",
                    transition: "background .15s",
                    flexShrink: 0,
                  }}
                >
                  Propose update
                </button>
              </div>
            </div>

            {proposalState === "proposed" && (
              <div
                style={{
                  marginTop: 18,
                  background: "#FFFFFF",
                  border: "1px solid #EBEFF4",
                  borderRadius: 20,
                  padding: 20,
                  boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
                  animation: "fdUp .3s ease both",
                }}
              >
                <div
                  style={{ display: "flex", alignItems: "center", gap: 9 }}
                >
                  <svg
                    width="17"
                    height="17"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#5463D6"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z" />
                  </svg>
                  <span
                    style={{
                      flex: 1,
                      fontSize: 15,
                      fontWeight: 700,
                      color: "#18181D",
                    }}
                  >
                    Proposed change
                  </span>
                  <span
                    style={{
                      background: "#EEF1FF",
                      color: "#37458A",
                      fontSize: "11.5px",
                      fontWeight: 700,
                      padding: "4px 10px",
                      borderRadius: 999,
                    }}
                  >
                    Needs your OK
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textTransform: "uppercase",
                    color: "#737685",
                    marginTop: 16,
                  }}
                >
                  Fall &amp; winter closures
                </div>
                <div
                  style={{
                    marginTop: 10,
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      background: "#FDEFF2",
                      borderRadius: 10,
                      padding: "11px 13px",
                    }}
                  >
                    <span
                      style={{
                        color: "#CF193A",
                        fontWeight: 800,
                        fontSize: 14,
                        lineHeight: 1.4,
                      }}
                    >
                      –
                    </span>
                    <span
                      style={{
                        fontSize: 14,
                        color: "#9497A6",
                        textDecoration: "line-through",
                        lineHeight: 1.4,
                      }}
                    >
                      Closed Thu Nov 27 — Thanksgiving Day
                    </span>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      background: "#E7F7EE",
                      borderRadius: 10,
                      padding: "11px 13px",
                    }}
                  >
                    <span
                      style={{
                        color: "#227A47",
                        fontWeight: 800,
                        fontSize: 14,
                        lineHeight: 1.4,
                      }}
                    >
                      +
                    </span>
                    <span
                      style={{
                        fontSize: 14,
                        color: "#18181D",
                        fontWeight: 600,
                        lineHeight: 1.4,
                      }}
                    >
                      Closed Thu Nov 27 &amp; Fri Nov 28 — Thanksgiving break
                    </span>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: 10,
                    marginTop: 18,
                  }}
                >
                  <button
                    className="fd-ghost"
                    onClick={() => {
                      setProposalState("idle");
                      setAuthorText("");
                    }}
                    style={{
                      background: "transparent",
                      color: "#5C5E6A",
                      border: "1px solid #EBEFF4",
                      borderRadius: 11,
                      padding: "10px 18px",
                      fontSize: "13.5px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all .15s",
                    }}
                  >
                    Discard
                  </button>
                  <button
                    className="fd-primary"
                    onClick={() => setProposalState("confirmed")}
                    style={{
                      background: "#5463D6",
                      color: "#FFFFFF",
                      border: "none",
                      borderRadius: 11,
                      padding: "10px 18px",
                      fontSize: "13.5px",
                      fontWeight: 700,
                      cursor: "pointer",
                      transition: "background .15s",
                    }}
                  >
                    Confirm &amp; publish
                  </button>
                </div>
              </div>
            )}

            {proposalState === "confirmed" && (
              <div
                style={{
                  marginTop: 18,
                  background: "#E7F7EE",
                  border: "1px solid #BFE9CF",
                  borderRadius: 16,
                  padding: "16px 18px",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  animation: "fdUp .3s ease both",
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 999,
                    background: "#3BBA6E",
                    display: "grid",
                    placeItems: "center",
                    flexShrink: 0,
                  }}
                >
                  <svg
                    width="17"
                    height="17"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#FFFFFF"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M20 6 9 17l-4-4" />
                  </svg>
                </div>
                <div>
                  <div
                    style={{
                      fontSize: "14.5px",
                      fontWeight: 700,
                      color: "#1A6B3D",
                    }}
                  >
                    Published — parents see this now.
                  </div>
                  <div
                    style={{
                      fontSize: "12.5px",
                      color: "#3E8259",
                      marginTop: 2,
                    }}
                  >
                    Logged to the changelog under your name.
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {nav === "changelog" && (
          <div style={{ padding: "30px 34px", maxWidth: 720 }}>
            <div
              style={{
                fontSize: 24,
                fontWeight: 800,
                color: "#18181D",
                letterSpacing: "-.01em",
              }}
            >
              Changelog
            </div>
            <div style={{ fontSize: 14, color: "#5C5E6A", marginTop: 4 }}>
              Every change to what parents see — who, what, and when.
            </div>
            <div style={{ marginTop: 24 }}>
              {changelog.map((c, idx) => (
                <div key={idx} style={{ display: "flex", gap: 15 }}>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      flexShrink: 0,
                    }}
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 999,
                        color: "#FFFFFF",
                        fontSize: 12,
                        fontWeight: 800,
                        display: "grid",
                        placeItems: "center",
                        background: c.color,
                      }}
                    >
                      {c.initials}
                    </div>
                    <div
                      style={{
                        width: 2,
                        flex: 1,
                        background: "#E4E8F1",
                        marginTop: 6,
                      }}
                    />
                  </div>
                  <div style={{ flex: 1, paddingBottom: 24 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 12,
                        alignItems: "baseline",
                      }}
                    >
                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: "#18181D",
                        }}
                      >
                        {c.who}
                      </span>
                      <span
                        style={{
                          fontSize: 12,
                          color: "#737685",
                          flexShrink: 0,
                        }}
                      >
                        {c.when}
                      </span>
                    </div>
                    <div
                      style={{ fontSize: 14, color: "#5C5E6A", marginTop: 3 }}
                    >
                      {c.what}
                    </div>
                    {c.isDiff && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 9,
                          marginTop: 11,
                          flexWrap: "wrap",
                        }}
                      >
                        <span
                          style={{
                            background: "#F3F4F8",
                            color: "#9497A6",
                            textDecoration: "line-through",
                            fontSize: "12.5px",
                            fontWeight: 600,
                            padding: "5px 11px",
                            borderRadius: 8,
                          }}
                        >
                          {c.before}
                        </span>
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#C4C8D4"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M5 12h14" />
                          <path d="m12 5 7 7-7 7" />
                        </svg>
                        <span
                          style={{
                            background: "#E7F7EE",
                            color: "#227A47",
                            fontSize: "12.5px",
                            fontWeight: 700,
                            padding: "5px 11px",
                            borderRadius: 8,
                          }}
                        >
                          {c.after}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Conflict modal */}
      {conflictOpen && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(30,37,73,.55)",
            display: "grid",
            placeItems: "center",
            padding: 24,
            zIndex: 60,
            animation: "fdUp .2s ease both",
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: 22,
              maxWidth: 540,
              width: "100%",
              boxShadow: "0 40px 80px -20px rgba(30,37,73,.5)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "22px 24px 18px",
                display: "flex",
                gap: 13,
                alignItems: "flex-start",
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 12,
                  background: "#FFF1DE",
                  display: "grid",
                  placeItems: "center",
                  flexShrink: 0,
                }}
              >
                <svg
                  width="21"
                  height="21"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#E08A0B"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                  <path d="M12 9v4" />
                  <path d="M12 17h.01" />
                </svg>
              </div>
              <div>
                <div
                  style={{
                    fontSize: 17,
                    fontWeight: 800,
                    color: "#18181D",
                    letterSpacing: "-.01em",
                  }}
                >
                  This conflicts with a fact on file
                </div>
                <div
                  style={{
                    fontSize: "13.5px",
                    color: "#5C5E6A",
                    marginTop: 3,
                    lineHeight: 1.45,
                  }}
                >
                  Two answers can&apos;t both be right. Which one should parents
                  see?
                </div>
              </div>
            </div>
            <div
              style={{
                padding: "0 24px",
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
              }}
            >
              <div
                style={{
                  border: "1px solid #EBEFF4",
                  borderRadius: 14,
                  padding: 15,
                }}
              >
                <div
                  style={{
                    fontSize: "11.5px",
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textTransform: "uppercase",
                    color: "#737685",
                  }}
                >
                  Currently on file
                </div>
                <div
                  style={{
                    fontSize: 19,
                    fontWeight: 800,
                    color: "#18181D",
                    marginTop: 9,
                  }}
                >
                  Opens 7:00 AM
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "#737685",
                    marginTop: 8,
                    lineHeight: 1.4,
                  }}
                >
                  Source: Hours &amp; Schedule
                  <br />
                  Set 3 months ago
                </div>
              </div>
              <div
                style={{
                  border: "1.5px solid #B1BAFF",
                  background: "#F5F7FF",
                  borderRadius: 14,
                  padding: 15,
                }}
              >
                <div
                  style={{
                    fontSize: "11.5px",
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textTransform: "uppercase",
                    color: "#5463D6",
                  }}
                >
                  Your update
                </div>
                <div
                  style={{
                    fontSize: 19,
                    fontWeight: 800,
                    color: "#37458A",
                    marginTop: 9,
                  }}
                >
                  Opens 6:30 AM
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "#737685",
                    marginTop: 8,
                    lineHeight: 1.4,
                  }}
                >
                  From your message
                  <br />
                  Just now
                </div>
              </div>
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
                padding: "20px 24px",
                marginTop: 18,
                borderTop: "1px solid #EBEFF4",
              }}
            >
              <button
                className="fd-ghost"
                onClick={() => setConflictOpen(false)}
                style={{
                  background: "transparent",
                  color: "#5C5E6A",
                  border: "1px solid #EBEFF4",
                  borderRadius: 11,
                  padding: "11px 18px",
                  fontSize: "13.5px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all .15s",
                }}
              >
                Keep 7:00 AM
              </button>
              <button
                className="fd-primary"
                onClick={() => {
                  setConflictOpen(false);
                  setProposalState("confirmed");
                  setAuthorText("");
                }}
                style={{
                  background: "#5463D6",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: 11,
                  padding: "11px 18px",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                  transition: "background .15s",
                }}
              >
                Use 6:30 AM
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
