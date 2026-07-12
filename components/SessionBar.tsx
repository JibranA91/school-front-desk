"use client";

import { signOut } from "next-auth/react";
import Link from "next/link";
import type { CSSProperties } from "react";

function pill(active: boolean): CSSProperties {
  return {
    padding: "7px 16px",
    borderRadius: 999,
    fontSize: 13,
    fontWeight: 700,
    textDecoration: "none",
    background: active ? "#5463D6" : "transparent",
    color: active ? "#FFFFFF" : "#5C5E6A",
    transition: "all .15s",
  };
}

export default function SessionBar({
  name,
  role,
  active,
}: {
  name: string;
  role?: string;
  active: "parent" | "operator";
}) {
  return (
    <div
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
      {/* Operators can preview the parent front desk; parents cannot. */}
      {role === "operator" && (
        <div
          style={{
            display: "flex",
            gap: 4,
            padding: 4,
            background: "#FFFFFF",
            border: "1px solid #EBEFF4",
            borderRadius: 999,
            boxShadow: "0 6px 22px rgba(24,24,29,.08)",
          }}
        >
          <Link href="/" style={pill(active === "parent")}>
            Parent
          </Link>
          <Link href="/operator" style={pill(active === "operator")}>
            Operator
          </Link>
        </div>
      )}

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
          onClick={() => signOut({ callbackUrl: "/login" })}
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
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
