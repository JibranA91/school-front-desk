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

// Stacked sections, most-actionable first.
const GROUPS: { kind: string; label: string }[] = [
  { kind: "contradiction", label: "Conflicts" },
  { kind: "redundancy", label: "Duplicates" },
  { kind: "outdated", label: "Expiring soon" },
];

type Meta = { name: string; origin: string; enabled: boolean; created: string | null };

const fmtDate = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? null
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};

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
        m[e.id] = {
          name: e.name,
          origin: e.origin,
          enabled: e.enabled ?? true,
          created: e.created_at ?? null,
        };
      setMeta(m);
    } catch {
      /* labels/dates are best-effort */
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
  const pending = findings.filter((f) => !applied.has(f.id));
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
          {sweptCount > 0 && (
            <div style={{ fontSize: 13, color: "#227A47", marginBottom: 12 }}>
              Auto-handled: {swept!.removed.length} expired removed,{" "}
              {swept!.restored.length} restored.
            </div>
          )}

          {findings.length === 0 || pending.length === 0 ? (
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
              {findings.length === 0
                ? "✓ Nothing to clean up — the knowledge base looks healthy."
                : "✓ All caught up — every finding reviewed."}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
              {GROUPS.map((g) => {
                const queue = pending.filter((f) => f.kind === g.kind);
                if (queue.length === 0) return null;
                const k = KIND[g.kind];
                const f = queue[0];
                const peeks = Math.min(2, queue.length - 1);
                return (
                  <div key={g.kind}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 800,
                          letterSpacing: ".03em",
                          textTransform: "uppercase",
                          color: k.color,
                        }}
                      >
                        {g.label}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#9497A6" }}>
                        {queue.length} left
                      </span>
                    </div>
                    {/* Card deck — one at a time; resolving or dismissing reveals the next. */}
                    <div style={{ position: "relative", marginBottom: peeks * 6 }}>
                      {Array.from({ length: peeks }).map((_, i) => (
                        <div
                          key={i}
                          style={{
                            position: "absolute",
                            left: 9 * (i + 1),
                            right: 9 * (i + 1),
                            bottom: -6 * (i + 1),
                            height: 26,
                            background: "#F4F6FB",
                            border: "1px solid #EBEFF4",
                            borderRadius: 12,
                            zIndex: 0,
                          }}
                        />
                      ))}
                      <div style={{ position: "relative", zIndex: 1 }}>
                        <FindingRow
                          key={f.id}
                          f={f}
                          label={label}
                          meta={meta}
                          busy={busy}
                          applied={false}
                          onDelete={(id) => act(f.id, () => deleteEntity(id))}
                          onDisable={(id, key) => act(key, () => setEntityEnabled(id, false))}
                          onDismiss={() => dismiss(f.id)}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
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
  const added = (id: string) => fmtDate(meta[id]?.created);

  // Conflicts: prefer the fact added later — recommend turning off the older one.
  let conflict: { newer: string; older: string } | null = null;
  if (f.kind === "contradiction" && f.entities.length === 2) {
    const [x, y] = f.entities;
    const cx = meta[x]?.created ?? "";
    const cy = meta[y]?.created ?? "";
    conflict = cx >= cy ? { newer: x, older: y } : { newer: y, older: x };
  }

  return (
    <div
      style={{
        background: "#FBFCFE",
        border: "1px solid #EBEFF4",
        borderRadius: 12,
        padding: "12px 14px",
      }}
    >
      {/* Header: badge + dismiss/applied. Summary lives on its own line below. */}
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
        <div style={{ flex: 1 }} />
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

      <div style={{ fontSize: 14, fontWeight: 600, color: "#18181D", marginTop: 8, lineHeight: 1.4 }}>
        {f.summary}
      </div>
      <div style={{ fontSize: 12.5, color: "#737685", marginTop: 6, lineHeight: 1.5 }}>
        {f.rationale}
      </div>

      {!applied && f.kind === "contradiction" && conflict && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          {[conflict.newer, conflict.older].map((id) => {
            const isNewer = id === conflict!.newer;
            const d = added(id);
            return (
              <div
                key={id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  background: "#FFFFFF",
                  border: "1px solid #EBEFF4",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#18181D" }}>
                    {label(id)}
                    {isNewer && (
                      <span
                        style={{
                          marginLeft: 6,
                          fontSize: 10.5,
                          fontWeight: 700,
                          color: "#227A47",
                          background: "#E7F7EE",
                          borderRadius: 999,
                          padding: "2px 7px",
                        }}
                      >
                        Newer · keep
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11.5, color: "#9497A6", marginTop: 2 }}>
                    {d ? `Added ${d}` : "Date unknown"}
                  </div>
                </div>
                <ActionBtn
                  label="Turn off"
                  primary={!isNewer}
                  disabled={busy === `${f.id}:${id}`}
                  onClick={() => onDisable(id, `${f.id}:${id}`)}
                />
              </div>
            );
          })}
          <div style={{ fontSize: 12, color: "#5C5E6A" }}>
            Recommended: keep the newer fact, turn off the older one.
          </div>
        </div>
      )}

      {!applied && f.kind === "contradiction" && !conflict && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          {f.entities
            .filter((id) => meta[id]?.enabled !== false)
            .map((id) => (
              <ActionBtn
                key={id}
                label={`Turn off "${label(id)}"`}
                disabled={busy === `${f.id}:${id}`}
                onClick={() => onDisable(id, `${f.id}:${id}`)}
              />
            ))}
        </div>
      )}

      {!applied && f.kind === "redundancy" && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 11.5, color: "#9497A6", marginBottom: 8 }}>
            {f.action.keep && (
              <>
                Keep{" "}
                <span style={{ color: "#5C5E6A", fontWeight: 600 }}>{label(f.action.keep)}</span>
                {added(f.action.keep) ? ` (added ${added(f.action.keep)})` : ""}.{" "}
              </>
            )}
            {f.action.entity_id && (
              <>
                Remove {label(f.action.entity_id)}
                {added(f.action.entity_id) ? ` (added ${added(f.action.entity_id)})` : ""}.
              </>
            )}
          </div>
          {f.action.type === "delete" && (
            <ActionBtn
              label="Delete the duplicate"
              danger
              disabled={busy === f.id}
              onClick={() => onDelete(f.action.entity_id!)}
            />
          )}
          {f.action.type === "disable" && (
            <ActionBtn
              label="Disable the duplicate"
              disabled={busy === f.id}
              onClick={() => onDisable(f.action.entity_id!, f.id)}
            />
          )}
          {f.action.type === "merge_needed" && (
            <span style={{ fontSize: 12.5, color: "#B5710A" }}>
              Keeps unique links — needs a merge (coming soon).
            </span>
          )}
        </div>
      )}

      {!applied && f.kind === "outdated" && (
        <div style={{ marginTop: 10, fontSize: 12.5, color: "#737685" }}>
          {added(f.entities[0]) ? `Added ${added(f.entities[0])} · ` : ""}
          Auto-removes on its date — no action needed.
        </div>
      )}
    </div>
  );
}

function ActionBtn({
  label,
  onClick,
  danger,
  primary,
  disabled,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  primary?: boolean;
  disabled?: boolean;
}) {
  const style = primary
    ? { bg: "#5463D6", color: "#FFFFFF", border: "#5463D6" }
    : danger
      ? { bg: "#FDEFF2", color: "#CF193A", border: "#F6C9D2" }
      : { bg: "#F5F7FF", color: "#5463D6", border: "#DCE1FF" };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        border: `1px solid ${style.border}`,
        background: style.bg,
        color: style.color,
        borderRadius: 8,
        padding: "6px 12px",
        fontSize: 12.5,
        fontWeight: 700,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.6 : 1,
        flexShrink: 0,
        maxWidth: "100%",
      }}
    >
      {label}
    </button>
  );
}
