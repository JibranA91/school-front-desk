"use client";

import { useEffect, useMemo, useState } from "react";

import {
  deleteEntity,
  fetchEntities,
  originStyles,
  setEntityEnabled,
  updateEntity,
  type EntityOrigin,
  type KbEntityDetail,
} from "@/lib/frontDesk";

type Filter = "all" | EntityOrigin;

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "seed", label: "Curated" },
  { key: "authored", label: "Operator" },
  { key: "handbook", label: "Handbook" },
];

const card = {
  marginTop: 18,
  background: "#FFFFFF",
  border: "1px solid #EBEFF4",
  borderRadius: 20,
  padding: 20,
  boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
} as const;

/** Turn an attribute value into an editable string, and back. */
const toStr = (v: unknown) =>
  v == null ? "" : typeof v === "string" ? v : JSON.stringify(v);

export default function EntityInspector({
  reloadToken = 0,
  onChanged,
}: {
  reloadToken?: number;
  onChanged?: () => void;
}) {
  const [entities, setEntities] = useState<KbEntityDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<KbEntityDetail | null>(null);
  const [localReload, setLocalReload] = useState(0);

  const refresh = () => setLocalReload((n) => n + 1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchEntities()
      .then((data) => {
        if (cancelled) return;
        setEntities(data);
        setError(null);
      })
      .catch(() => !cancelled && setError("Couldn't load knowledge."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [reloadToken, localReload]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: entities.length, seed: 0, authored: 0, handbook: 0 };
    for (const e of entities) c[e.origin]++;
    return c;
  }, [entities]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entities.filter((e) => {
      if (filter !== "all" && e.origin !== filter) return false;
      if (!q) return true;
      return (
        e.name.toLowerCase().includes(q) ||
        e.type.toLowerCase().includes(q) ||
        e.id.toLowerCase().includes(q)
      );
    });
  }, [entities, query, filter]);

  const afterMutate = () => {
    setSelected(null);
    refresh();
    onChanged?.();
  };

  return (
    <div style={card}>
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
          <path d="M4 6h16M4 12h16M4 18h10" />
        </svg>
        <span style={{ flex: 1 }}>Browse &amp; edit knowledge</span>
        <span style={{ fontSize: "12.5px", color: "#737685", fontWeight: 600 }}>
          {counts.all} entries
        </span>
      </div>
      <div style={{ fontSize: "13.5px", color: "#5C5E6A", marginTop: 6, lineHeight: 1.5 }}>
        Inspect every fact the front desk can draw on. Edit a value directly, or
        remove one that&apos;s out of date.
      </div>

      {/* Search + origin filters */}
      <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, type, or id…"
          style={{
            flex: "1 1 220px",
            background: "#F7F9FB",
            border: "1px solid #EBEFF4",
            borderRadius: 11,
            padding: "10px 13px",
            fontSize: "13.5px",
            color: "#18181D",
          }}
        />
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {FILTERS.map((f) => {
            const active = filter === f.key;
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  padding: "8px 13px",
                  borderRadius: 999,
                  border: active ? "1px solid #5463D6" : "1px solid #E3E8FF",
                  background: active ? "#5463D6" : "#F5F7FF",
                  color: active ? "#FFFFFF" : "#5463D6",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all .15s",
                }}
              >
                {f.label}
                <span style={{ opacity: 0.7 }}> {counts[f.key]}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* List */}
      <div
        className="fd-scroll"
        style={{
          marginTop: 14,
          maxHeight: 340,
          overflowY: "auto",
          border: "1px solid #EBEFF4",
          borderRadius: 14,
        }}
      >
        {loading && (
          <div style={{ padding: 20, fontSize: 13, color: "#737685" }}>Loading…</div>
        )}
        {error && (
          <div style={{ padding: 20, fontSize: 13, color: "#CF193A" }}>{error}</div>
        )}
        {!loading && !error && visible.length === 0 && (
          <div style={{ padding: 20, fontSize: 13, color: "#737685" }}>
            No entries match.
          </div>
        )}
        {visible.map((e, i) => {
          const o = originStyles[e.origin];
          return (
            <button
              key={e.id}
              onClick={() => setSelected(e)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                width: "100%",
                textAlign: "left",
                background: "transparent",
                border: "none",
                borderTop: i === 0 ? "none" : "1px solid #F0F2F7",
                padding: "12px 14px",
                cursor: "pointer",
                fontFamily: "inherit",
                opacity: e.enabled === false ? 0.5 : 1,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "13.5px",
                    fontWeight: 700,
                    color: "#18181D",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {e.name}
                </div>
                <div style={{ fontSize: "11.5px", color: "#9497A6", marginTop: 2 }}>
                  {e.type} · {e.connections} link{e.connections === 1 ? "" : "s"}
                </div>
              </div>
              {e.enabled === false && (
                <span
                  style={{
                    background: "#F0F2F7",
                    color: "#737685",
                    fontSize: "10.5px",
                    fontWeight: 700,
                    padding: "3px 9px",
                    borderRadius: 999,
                    flexShrink: 0,
                  }}
                >
                  Off
                </span>
              )}
              <span
                style={{
                  background: o.bg,
                  color: o.color,
                  fontSize: "10.5px",
                  fontWeight: 700,
                  padding: "3px 9px",
                  borderRadius: 999,
                  flexShrink: 0,
                }}
              >
                {o.label}
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
                style={{ flexShrink: 0 }}
              >
                <path d="m9 18 6-6-6-6" />
              </svg>
            </button>
          );
        })}
      </div>

      {selected && (
        <EntityEditor
          entity={selected}
          onClose={() => setSelected(null)}
          onSaved={afterMutate}
          onDeleted={afterMutate}
        />
      )}
    </div>
  );
}

function EntityEditor({
  entity,
  onClose,
  onSaved,
  onDeleted,
}: {
  entity: KbEntityDetail;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(entity.name);
  const [type, setType] = useState(entity.type);
  const [fields, setFields] = useState<{ key: string; value: string }[]>(
    Object.entries(entity.attributes).map(([k, v]) => ({ key: k, value: toStr(v) })),
  );
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const o = originStyles[entity.origin];
  const isHandbook = entity.origin === "handbook";
  const enabled = entity.enabled ?? true;

  const toggleEnabled = async () => {
    setBusy(true);
    setErr(null);
    try {
      await setEntityEnabled(entity.id, !enabled);
      onSaved(); // refresh the list + close; the row reflects the new state
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Toggle failed");
      setBusy(false);
    }
  };

  const setValue = (i: number, value: string) =>
    setFields((f) => f.map((row, j) => (j === i ? { ...row, value } : row)));

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const attributes: Record<string, unknown> = {};
      for (const { key, value } of fields) if (key) attributes[key] = value;
      await updateEntity(entity.id, { name, type, attributes });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setErr(null);
    try {
      await deleteEntity(entity.id);
      onDeleted();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
      setBusy(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(30,37,73,.55)",
        display: "grid",
        placeItems: "center",
        padding: 24,
        zIndex: 70,
        animation: "fdUp .2s ease both",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="fd-scroll"
        style={{
          background: "#FFFFFF",
          borderRadius: 22,
          maxWidth: 520,
          width: "100%",
          maxHeight: "86vh",
          overflowY: "auto",
          boxShadow: "0 40px 80px -20px rgba(30,37,73,.5)",
          padding: "24px 24px 20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              background: o.bg,
              color: o.color,
              fontSize: "11px",
              fontWeight: 700,
              padding: "3px 10px",
              borderRadius: 999,
            }}
          >
            {o.label}
          </span>
          <code style={{ fontSize: "11.5px", color: "#9497A6" }}>{entity.id}</code>
        </div>

        <label style={labelStyle}>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />

        <label style={labelStyle}>Type</label>
        <input value={type} onChange={(e) => setType(e.target.value)} style={inputStyle} />

        <label style={labelStyle}>Attributes</label>
        {fields.length === 0 && (
          <div style={{ fontSize: "12.5px", color: "#9497A6" }}>No attributes.</div>
        )}
        {fields.map((f, i) => (
          <div key={f.key} style={{ marginTop: 8 }}>
            <div style={{ fontSize: "11.5px", fontWeight: 700, color: "#737685" }}>
              {f.key}
            </div>
            <textarea
              value={f.value}
              onChange={(e) => setValue(i, e.target.value)}
              style={{ ...inputStyle, marginTop: 4, minHeight: 44, resize: "vertical" }}
            />
          </div>
        ))}

        {entity.origin === "seed" && (
          <div
            style={{
              marginTop: 14,
              background: "#FFF7DB",
              border: "1px solid #F0E2A8",
              borderRadius: 10,
              padding: "9px 12px",
              fontSize: "12px",
              color: "#8A6D12",
            }}
          >
            This is curated demo data — the seed backbone. Edits and deletes stick
            until the database is reseeded.
          </div>
        )}

        {isHandbook && (
          <div
            style={{
              marginTop: 14,
              background: "#FFF1DE",
              border: "1px solid #FFE1BB",
              borderRadius: 10,
              padding: "9px 12px",
              fontSize: "12px",
              color: "#8A5A00",
            }}
          >
            Handbook facts are the source of record — read-only. You can&apos;t edit
            or delete this, but you can switch it off (hide it from parents) below.
            To change what parents see, add an operator fact that overrides it.
          </div>
        )}

        {err && (
          <div style={{ marginTop: 12, fontSize: "12.5px", color: "#CF193A", fontWeight: 600 }}>
            {err}
          </div>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginTop: 20,
          }}
        >
          <button
            onClick={toggleEnabled}
            disabled={busy}
            title={
              enabled ? "Hide this fact from parents" : "Show this fact to parents"
            }
            style={{
              background: enabled ? "transparent" : "#E7F7EE",
              color: enabled ? "#8A5A00" : "#227A47",
              border: `1px solid ${enabled ? "#FFE1BB" : "#BFE9CF"}`,
              borderRadius: 11,
              padding: "10px 16px",
              fontSize: "13px",
              fontWeight: 700,
              cursor: busy ? "default" : "pointer",
            }}
          >
            {enabled ? "Turn off" : "Turn on"}
          </button>
          {!isHandbook &&
            (!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={busy}
                style={{
                  background: "transparent",
                  color: "#CF193A",
                  border: "1px solid #F6C9D2",
                  borderRadius: 11,
                  padding: "10px 16px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: busy ? "default" : "pointer",
                }}
              >
                Delete
              </button>
            ) : (
              <button
                onClick={remove}
                disabled={busy}
                style={{
                  background: "#CF193A",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: 11,
                  padding: "10px 16px",
                  fontSize: "13px",
                  fontWeight: 700,
                  cursor: busy ? "default" : "pointer",
                }}
              >
                {busy ? "Removing…" : "Confirm delete"}
              </button>
            ))}
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            disabled={busy}
            style={{
              background: "transparent",
              color: "#5C5E6A",
              border: "1px solid #EBEFF4",
              borderRadius: 11,
              padding: "10px 18px",
              fontSize: "13.5px",
              fontWeight: 600,
              cursor: busy ? "default" : "pointer",
            }}
          >
            {isHandbook ? "Close" : "Cancel"}
          </button>
          {!isHandbook && (
            <button
              onClick={save}
              disabled={busy}
              style={{
                background: "#5463D6",
                color: "#FFFFFF",
                border: "none",
                borderRadius: 11,
                padding: "10px 18px",
                fontSize: "13.5px",
                fontWeight: 700,
                cursor: busy ? "default" : "pointer",
                opacity: busy ? 0.7 : 1,
              }}
            >
              {busy ? "Saving…" : "Save changes"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const labelStyle = {
  display: "block",
  fontSize: "11.5px",
  fontWeight: 700,
  letterSpacing: ".04em",
  textTransform: "uppercase",
  color: "#737685",
  marginTop: 16,
  marginBottom: 6,
} as const;

const inputStyle = {
  width: "100%",
  background: "#F7F9FB",
  border: "1px solid #EBEFF4",
  borderRadius: 11,
  padding: "10px 13px",
  fontSize: "13.5px",
  color: "#18181D",
  fontFamily: "inherit",
  lineHeight: 1.5,
} as const;
