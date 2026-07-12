"use client";

import { useState, type CSSProperties } from "react";
import ParentView from "@/components/ParentView";
import OperatorView from "@/components/OperatorView";

type View = "parent" | "operator";

function toggleBtn(active: boolean): CSSProperties {
  return {
    padding: "9px 20px",
    borderRadius: 999,
    border: "none",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: 14,
    fontWeight: 700,
    background: active ? "#5463D6" : "transparent",
    color: active ? "#FFFFFF" : "#5C5E6A",
    transition: "all .15s",
  };
}

export default function Home() {
  const [view, setView] = useState<View>("parent");

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#F7F9FB",
        color: "#18181D",
        padding: "74px 20px 40px",
        position: "relative",
      }}
    >
      <div
        style={{
          position: "fixed",
          top: 16,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 40,
          display: "flex",
          gap: 4,
          padding: 4,
          background: "#FFFFFF",
          border: "1px solid #EBEFF4",
          borderRadius: 999,
          boxShadow: "0 6px 22px rgba(24,24,29,.08)",
        }}
      >
        <button
          onClick={() => setView("parent")}
          style={toggleBtn(view === "parent")}
        >
          Parent front desk
        </button>
        <button
          onClick={() => setView("operator")}
          style={toggleBtn(view === "operator")}
        >
          Operator
        </button>
      </div>

      {view === "parent" ? <ParentView /> : <OperatorView />}
    </div>
  );
}
