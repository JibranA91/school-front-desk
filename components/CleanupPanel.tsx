"use client";

import { useState } from "react";

import {
  runCleanupScan,
  setEntityEnabled,
  deleteEntity,
  fetchEntities,
  type CleanupFinding,
  type CleanupResult,
} from "@/lib/frontDesk";

const KIND: Record<string, { bg: string; color: string; label: string }> = {
  outdated: { bg: "#FFF1DE", color: "#B5710A", label: "Expiring" },
  redundancy: { bg: "#EEF1FF", color: "#4B57B8", label: "Duplicate" },
  contradiction: { bg: "#FDEFF2", color: "#CF193A", label: "Conflict" },
};

type Meta = { name: string; origin: string; enabled: boolean };

export default function CleanupPanel({ onChanged }: { onChanged: () => void }) {
  const [mode, setMode] = useState<"quick" | "deep">("quick");
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState("");
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [applied, setApplied] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, Meta>>({});

  const loadMeta = async () => {
    try {
      const ents = await fetchEntities();
      const m: Record<string, Meta> = {};
      for (const e of ents)
        m[e.id] = { name: e.name, origin: e.origin, enabled: e.enabled ?? true };
      setMeta(m);
    } catch {
      /* labels are best-effort */
    }
  };

  const run = async () => {
    setRunning(true);
    setError("");
    setResult(null);
    setDismissed(new Set());
    setApplied(new Set());
    try {
      const r = await runCleanupScan(mode, setPhase);
      setResult(r);
      loadMeta();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const label = (id: string) => meta[id]?.name ?? id;

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError("");
    try {
      await fn();
      setApplied((s) => new Set(s).add(key));
      onChanged();
      loadMeta();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const dismiss = (id: string) => setDismissed((s) => new Set(s).add(id));

  const findings = (result?.findings ?? []).filter((f) => !dismissed.has(f.id));
  const swept = result?.swept;
  const sweptCount = (swept?.removed.length ?? 0) + (swept?.restored.length ?? 0);

  return (
    <div
      style={{
        marginTop: 18,
        background: "#FFFFFF",
        border: "1px solid #EBEFF4",
        borderRadius: 20,
        padding: 20,
        boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#5463D6"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ flexShrink: 0 }}
        >
          <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        </svg>
        <span style={{ fontSize: 15, fontWeight: 700, color: "#18181D" }}>
          Clean up the knowledge base
        </span>
      </div>
      <div style={{ fontSize: "13.5px", color: "#5C5E6A", marginTop: 6, lineHeight: 1.5 }}>
        Scans for stale, duplicate, and conflicting facts.{" "}
        {mode === "quick" ? "Quick" : "Deep"} —{" "}
        {mode === "quick"
          ? "deterministic checks only (instant, no AI)."
          : "adds AI confirmation of near-duplicates and subtle conflicts."}{" "}
        Nothing changes without your click.
      </div>

      {/* Controls on their own row so the title never competes for width */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
          marginTop: 14,
        }}
      >
        {/* Quick / Deep toggle */}
        <div style={{ display: "flex", background: "#F0F2F7", borderRadius: 10, padding: 3 }}>
          {(["quick", "deep"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              disabled={running}
              style={{
                border: "none",
                background: mode === m ? "#FFFFFF" : "transparent",
                color: mode === m ? "#18181D" : "#737685",
                boxShadow: mode === m ? "0 1px 3px rgba(24,24,29,.12)" : "none",
                borderRadius: 8,
                padding: "6px 14px",
                fontSize: 12.5,
                fontWeight: 700,
                cursor: running ? "default" : "pointer",
                textTransform: "capitalize",
              }}
            >
              {m}
            </button>
          ))}
        </div>
        <div style={{ flex: 1, minWidth: 8 }} />
        <button
          onClick={run}
          disabled={running}
          className="fd-primary"
          style={{
            background: "#5463D6",
            color: "#FFFFFF",
            border: "none",
            borderRadius: 10,
            padding: "9px 18px",
            fontSize: 13.5,
            fontWeight: 700,
            cursor: running ? "default" : "pointer",
            opacity: running ? 0.7 : 1,
          }}
        >
          {running ? "Scanning…" : "Run cleanup"}
        </button>
      </div>

      {running && phase && (
        <div className="fd-shimmer" style={{ marginTop: 14, fontSize: 13, fontWeight: 600 }}>
          {phase}
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 14,
            fontSize: 13,
            color: "#CF193A",
            background: "#FDEFF2",
            border: "1px solid #F8CBD6",
            borderRadius: 10,
            padding: "9px 12px",
          }}
        >
          {error}
        </div>
      )}

      {result && !running && (
        <div style={{ marginTop: 16 }}>
          {/* Auto-handled sweep summary */}
          {sweptCount > 0 && (
            <div style={{ fontSize: 13, color: "#227A47", marginBottom: 12 }}>
              Auto-handled: {swept!.removed.length} expired removed,{" "}
              {swept!.restored.length} restored.
            </div>
          )}

          {findings.length === 0 ? (
            <div
              style={{
                fontSize: 14,
                color: "#227A47",
                background: "#E7F7EE",
                border: "1px solid #BFE9CF",
                borderRadius: 12,
                padding: "12px 14px",
                fontWeight: 600,
              }}
            >
              ✓ Nothing to clean up — the knowledge base looks healthy.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {findings.map((f) => (
                <FindingRow
                  key={f.id}
                  f={f}
                  label={label}
                  meta={meta}
                  busy={busy}
                  applied={applied.has(f.id)}
                  onDelete={(id) => act(f.id, () => deleteEntity(id))}
                  onDisable={(id, key) => act(key, () => setEntityEnabled(id, false))}
                  onDismiss={() => dismiss(f.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FindingRow({
  f,
  label,
  meta,
  busy,
  applied,
  onDelete,
  onDisable,
  onDismiss,
}: {
  f: CleanupFinding;
  label: (id: string) => string;
  meta: Record<string, Meta>;
  busy: string | null;
  applied: boolean;
  onDelete: (id: string) => void;
  onDisable: (id: string, key: string) => void;
  onDismiss: () => void;
}) {
  const k = KIND[f.kind] ?? { bg: "#EEF1FF", color: "#4B57B8", label: f.kind };
  return (
    <div
      style={{
        background: "#FBFCFE",
        border: "1px solid #EBEFF4",
        borderRadius: 12,
        padding: "12px 14px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: k.color,
            background: k.bg,
            borderRadius: 999,
            padding: "3px 9px",
          }}
        >
          {k.label}
        </span>
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: "#18181D" }}>
          {f.summary}
        </span>
        {applied ? (
          <span style={{ fontSize: 13, fontWeight: 700, color: "#227A47" }}>✓ Applied</span>
        ) : (
          <button
            onClick={onDismiss}
            className="fd-ghost"
            style={{
              border: "1px solid #EBEFF4",
              background: "transparent",
              color: "#737685",
              borderRadius: 8,
              padding: "5px 10px",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Dismiss
          </button>
        )}
      </div>
      <div style={{ fontSize: 12.5, color: "#737685", marginTop: 6, lineHeight: 1.5 }}>
        {f.rationale}
      </div>

      {!applied && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          {f.kind === "redundancy" && f.action.type === "delete" && (
            <ActionBtn
              label={`Delete “${label(f.action.entity_id!)}”`}
              danger
              disabled={busy === f.id}
              onClick={() => onDelete(f.action.entity_id!)}
            />
          )}
          {f.kind === "redundancy" && f.action.type === "disable" && (
            <ActionBtn
              label={`Disable “${label(f.action.entity_id!)}”`}
              disabled={busy === f.id}
              onClick={() => onDisable(f.action.entity_id!, f.id)}
            />
          )}
          {f.kind === "redundancy" && f.action.type === "merge_needed" && (
            <span style={{ fontSize: 12.5, color: "#B5710A" }}>
              Keeps unique links — needs a merge (coming soon).
            </span>
          )}
          {f.kind === "contradiction" &&
            f.entities
              .filter((id) => meta[id]?.enabled !== false)
              .map((id) => (
                <ActionBtn
                  key={id}
                  label={`Turn off “${label(id)}”`}
                  disabled={busy === `${f.id}:${id}`}
                  onClick={() => onDisable(id, `${f.id}:${id}`)}
                />
              ))}
          {f.kind === "outdated" && (
            <span style={{ fontSize: 12.5, color: "#737685" }}>
              Auto-removes on its date — no action needed.
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ActionBtn({
  label,
  onClick,
  danger,
  disabled,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        border: `1px solid ${danger ? "#F6C9D2" : "#DCE1FF"}`,
        background: danger ? "#FDEFF2" : "#F5F7FF",
        color: danger ? "#CF193A" : "#5463D6",
        borderRadius: 8,
        padding: "6px 12px",
        fontSize: 12.5,
        fontWeight: 700,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {label}
    </button>
  );
}
