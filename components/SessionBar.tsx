"use client";

import { signOut } from "next-auth/react";

export default function SessionBar({ name }: { name: string }) {
  return (
    <div
      className="fd-sessionbar"
      style={{
        position: "fixed",
        top: 16,
        right: 20,
        zIndex: 50,
        display: "flex",
        gap: 10,
        alignItems: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "6px 8px 6px 14px",
          background: "#FFFFFF",
          border: "1px solid #EBEFF4",
          borderRadius: 999,
          boxShadow: "0 6px 22px rgba(24,24,29,.08)",
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 600, color: "#18181D" }}>
          {name}
        </span>
        <button
          onClick={async () => {
            // Clear the session, then navigate on the browser's own origin —
            // NextAuth's server-computed redirect can resolve to the container
            // bind host (0.0.0.0) behind the standalone server.
            await signOut({ redirect: false });
            window.location.href = "/login";
          }}
          className="fd-ghost"
          style={{
            border: "1px solid #EBEFF4",
            background: "transparent",
            color: "#5C5E6A",
            borderRadius: 999,
            padding: "6px 14px",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            transition: "all .15s",
            display: "flex",
            alignItems: "center",
            gap: 7,
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
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" x2="9" y1="12" y2="12" />
          </svg>
          <span>Sign out</span>
        </button>
      </div>
    </div>
  );
}
