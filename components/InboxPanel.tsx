"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import {
  fetchInbox,
  fetchThread,
  proposeChange,
  replyToParent,
  resolveInquiry,
  statusStyles,
  type Change,
  type InboxItem,
  type Msg,
  type Proposal,
  type Thread,
} from "@/lib/frontDesk";

type Tone = "amber" | "green" | "indigo";
const TONES: Record<Tone, { bg: string; fg: string; dot: string }> = {
  amber: { bg: "#FFF7ED", fg: "#B5710A", dot: "#FF9D17" },
  green: { bg: "#E7F7EE", fg: "#227A47", dot: "#3BBA6E" },
  indigo: { bg: "#EEF1FF", fg: "#4B57B8", dot: "#5463D6" },
};

/** Group key for dedup: the stored group_key, or a fallback derived from the
 *  question text (mirrors the backend) so older inquiries without one still
 *  collapse. */
function groupKeyOf(it: InboxItem): string {
  if (it.group_key) return it.group_key;
  const words = (it.text.toLowerCase().match(/[a-z0-9]+/g) ?? []).slice(0, 8);
  return words.join(" ");
}

/** Collapse duplicate questions into one row + a count. Input is assumed
 *  newest-first, so the kept row is the most recent occurrence. */
function collapse(items: InboxItem[]): { item: InboxItem; count: number }[] {
  const byKey = new Map<string, { item: InboxItem; count: number }>();
  const out: { item: InboxItem; count: number }[] = [];
  for (const it of items) {
    const key = groupKeyOf(it);
    if (!key) {
      out.push({ item: it, count: 1 });
      continue;
    }
    const existing = byKey.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      const entry = { item: it, count: 1 };
      byKey.set(key, entry);
      out.push(entry);
    }
  }
  return out;
}

// Friendly labels for the entity-type / theme topics stored on inquiries.
const TOPIC_LABEL: Record<string, string> = {
  Tuition: "Tuition & fees",
  Billing: "Billing",
  Hours: "Hours & schedule",
  Meal: "Meals",
  Health: "Health & illness",
  Policy: "Policies",
  Enrollment: "Enrollment & tours",
  Program: "Programs",
  Safety: "Safety",
  Behavior: "Behavior & guidance",
  Communication: "Communication",
  Supplies: "Clothing & supplies",
  Curriculum: "Curriculum",
  Holiday: "Holidays & closures",
  Attendance: "Attendance",
  Center: "Center info",
  Family: "Family",
};
const topicLabel = (t: string | null) => (t && TOPIC_LABEL[t]) || t || "Other";

export type GroupBy = "status" | "topic" | "family";
export const GROUP_BY_LABELS: Record<GroupBy, string> = {
  status: "Status",
  topic: "Topic",
  family: "Family",
};

const STATUS_RANK: Record<InboxItem["status"], number> = {
  escalated: 0,
  lowconf: 1,
  answered: 2,
  resolved: 3,
};

interface DisplayGroup {
  id: string;
  label: string;
  tone: Tone;
  rows: { item: InboxItem; count: number }[];
  hasAttention: boolean;
}

function groupTone(items: InboxItem[]): Tone {
  if (items.some((i) => i.status === "escalated" || i.status === "lowconf")) return "amber";
  if (items.some((i) => i.status === "answered")) return "green";
  return "indigo";
}

/** Partition inbox items into collapsible groups along the chosen dimension.
 *  Within a group, rows are status-then-recency sorted and deduped. */
function buildGroups(items: InboxItem[], groupBy: GroupBy): DisplayGroup[] {
  const sorted = [...items].sort(
    (a, b) =>
      STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
  );
  const keyOf = (it: InboxItem): string => {
    if (groupBy === "status") {
      if (it.status === "escalated" || it.status === "lowconf") return "Needs your attention";
      if (it.status === "resolved") return "Resolved";
      return "Answered by the AI";
    }
    if (groupBy === "topic") return topicLabel(it.topic);
    return it.who || "Unknown";
  };

  const buckets = new Map<string, InboxItem[]>();
  for (const it of sorted) {
    const k = keyOf(it);
    (buckets.get(k) ?? buckets.set(k, []).get(k)!).push(it);
  }

  const groups: DisplayGroup[] = [...buckets.entries()].map(([label, arr]) => ({
    id: `${groupBy}:${label}`,
    label,
    tone: groupTone(arr),
    rows: collapse(arr),
    hasAttention: arr.some((i) => i.status === "escalated" || i.status === "lowconf"),
  }));

  if (groupBy === "status") {
    const order = ["Needs your attention", "Answered by the AI", "Resolved"];
    groups.sort((a, b) => order.indexOf(a.label) - order.indexOf(b.label));
  } else {
    // Groups with pending attention float up; "Other" sinks; then by size.
    groups.sort(
      (a, b) =>
        Number(b.hasAttention) - Number(a.hasAttention) ||
        (a.label === "Other" ? 1 : b.label === "Other" ? -1 : 0) ||
        b.rows.length - a.rows.length ||
        a.label.localeCompare(b.label),
    );
  }
  return groups;
}

const SENSITIVE = new Set([
  "health",
  "allergy",
  "medication",
  "safety",
  "billing_dispute",
  "custody",
]);

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return `${Math.round(hrs / 24)} d ago`;
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  const t = TONES[tone];
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: t.bg,
        borderRadius: 12,
        padding: "9px 14px",
      }}
    >
      <span style={{ fontSize: 20, fontWeight: 800, color: t.fg, lineHeight: 1 }}>
        {value}
      </span>
      <span style={{ fontSize: "12.5px", fontWeight: 600, color: t.fg }}>{label}</span>
    </div>
  );
}

function InboxRow({
  item,
  count,
  dim,
  onClick,
}: {
  item: InboxItem;
  count: number;
  dim?: boolean;
  onClick: () => void;
}) {
  const s = statusStyles[item.status];
  return (
    <div
      className="fd-inbox-row"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "15px 18px",
        borderBottom: "1px solid #F0F3F8",
        cursor: "pointer",
        transition: "background .12s",
        opacity: dim ? 0.65 : 1,
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
        <div style={{ fontSize: 15, fontWeight: 600, color: "#18181D" }}>{item.text}</div>
        <div style={{ fontSize: "12.5px", color: "#737685", marginTop: 3 }}>
          {item.who} · {timeAgo(item.created_at)}
        </div>
      </div>
      {count > 1 && (
        <span
          style={{
            background: "#FFF1DE",
            color: "#B5710A",
            fontSize: 11,
            fontWeight: 800,
            padding: "3px 9px",
            borderRadius: 999,
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          {count} asked
        </span>
      )}
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
}

function CollapsibleGroup({
  group,
  collapsed,
  onToggle,
  onOpen,
}: {
  group: DisplayGroup;
  collapsed: boolean;
  onToggle: () => void;
  onOpen: (i: InboxItem) => void;
}) {
  const t = TONES[group.tone];
  return (
    <div style={{ marginTop: 16 }}>
      <button
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          width: "100%",
          textAlign: "left",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "6px 2px",
          marginBottom: 8,
        }}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#9AA0B4"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            flexShrink: 0,
            transform: collapsed ? "rotate(0deg)" : "rotate(90deg)",
            transition: "transform .15s",
          }}
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
        <span
          style={{ width: 8, height: 8, borderRadius: 999, background: t.dot, display: "inline-block" }}
        />
        <span
          style={{
            fontSize: 12,
            fontWeight: 800,
            letterSpacing: ".05em",
            textTransform: "uppercase",
            color: "#737685",
          }}
        >
          {group.label}
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: t.fg,
            background: t.bg,
            borderRadius: 999,
            padding: "1px 9px",
          }}
        >
          {group.rows.length}
        </span>
      </button>
      {!collapsed && (
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #EBEFF4",
            borderRadius: 16,
            overflow: "hidden",
            boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
          }}
        >
          {group.rows.map(({ item, count }) => (
            <InboxRow
              key={item.id}
              item={item}
              count={count}
              dim={item.status === "resolved"}
              onClick={() => onOpen(item)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TranscriptBubble({ m }: { m: Msg }) {
  const isUser = m.type === "user";
  const isStaff = m.type === "staff";
  const body = m.text ?? m.answer ?? "";
  return (
    <div
      style={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        maxWidth: "88%",
        background: isUser ? "#5463D6" : isStaff ? "#EAF7F7" : "#F1F4FF",
        color: isUser ? "#FFFFFF" : "#18181D",
        fontSize: "13.5px",
        lineHeight: 1.5,
        padding: "10px 13px",
        borderRadius: isUser ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
        whiteSpace: "pre-wrap",
      }}
    >
      {isStaff && (
        <div style={{ fontSize: 11, fontWeight: 700, color: "#12878A", marginBottom: 3 }}>
          {m.by ?? "Staff"} · staff reply
        </div>
      )}
      {body}
      {m.citation && !isUser && !isStaff && (
        <div style={{ fontSize: 11, color: "#737685", marginTop: 5 }}>{m.citation}</div>
      )}
      {Array.isArray(m.menu) && m.menu.length > 0 && (
        <div style={{ fontSize: 12, color: "#5C5E6A", marginTop: 5 }}>
          {m.menu.join(" · ")}
        </div>
      )}
    </div>
  );
}

const primaryBtn = (busy = false): CSSProperties => ({
  background: busy ? "#9AA3E6" : "#5463D6",
  color: "#FFFFFF",
  border: "none",
  borderRadius: 11,
  padding: "10px 18px",
  fontSize: "13.5px",
  fontWeight: 700,
  cursor: busy ? "default" : "pointer",
  transition: "background .15s",
});

const ghostBtn: CSSProperties = {
  background: "transparent",
  color: "#5C5E6A",
  border: "1px solid #EBEFF4",
  borderRadius: 11,
  padding: "10px 18px",
  fontSize: "13.5px",
  fontWeight: 600,
  cursor: "pointer",
};

export default function InboxPanel({
  onChanged,
  onOpenCount,
  resetSignal,
}: {
  onChanged?: () => void;
  onOpenCount?: (n: number) => void;
  resetSignal?: number; // bump to force back to the list view (e.g. sidebar "Inbox")
}) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Teach-and-fold flow state (per selected inquiry).
  const [replyText, setReplyText] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [stage, setStage] = useState<"idle" | "proposed" | "resolved">("idle");
  const [resolvedCount, setResolvedCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>("status");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const load = () =>
    fetchInbox()
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
    // Poll so newly-asked parent questions surface without a refresh.
    const poll = setInterval(load, 4000);
    return () => clearInterval(poll);
  }, []);

  // Sidebar "Inbox" (or any reset bump) returns from a detail to the list.
  useEffect(() => {
    setSelectedId(null);
  }, [resetSignal]);

  // Deduped counts per status for the at-a-glance stats (independent of grouping).
  const stats = useMemo(() => {
    const count = (fn: (i: InboxItem) => boolean) => collapse(items.filter(fn)).length;
    return {
      attention: count((i) => i.status === "escalated" || i.status === "lowconf"),
      answered: count((i) => i.status === "answered"),
      resolved: count((i) => i.status === "resolved"),
    };
  }, [items]);

  const grouped = useMemo(() => buildGroups(items, groupBy), [items, groupBy]);

  const toggleGroup = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  useEffect(() => {
    onOpenCount?.(stats.attention);
  }, [stats.attention, onOpenCount]);

  const selected = items.find((i) => i.id === selectedId) ?? null;

  const openDetail = (item: InboxItem) => {
    setSelectedId(item.id);
    setReplyText("");
    setProposal(null);
    setStage("idle");
    setResolvedCount(0);
    setErr(null);
  };

  const back = () => setSelectedId(null);

  const draft = async () => {
    const t = replyText.trim();
    if (!t || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const p = await proposeChange(t);
      setProposal(p);
      setStage("proposed");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't draft an update.");
    } finally {
      setBusy(false);
    }
  };

  const fold = async (changes: Change[]) => {
    if (!selected || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await resolveInquiry(selected.id, {
        changes,
        summary: proposal?.summary,
        acceptConflicts: true,
        resolutionText: replyText.trim() || undefined,
      });
      setResolvedCount(res.resolved.length);
      setStage("resolved");
      onChanged?.();
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't resolve.");
    } finally {
      setBusy(false);
    }
  };

  const markHandled = async () => {
    if (!selected || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await resolveInquiry(selected.id, {
        changes: [],
        resolutionText: replyText.trim() || "Handled by staff.",
      });
      setResolvedCount(res.resolved.length);
      setStage("resolved");
      onChanged?.();
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't resolve.");
    } finally {
      setBusy(false);
    }
  };

  const conflict = proposal?.changes.find((c) => c.is_conflict) ?? null;

  return (
    <div style={{ padding: "30px 34px" }}>
      {!selected ? (
        <>
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
            Escalations and knowledge gaps need you; everything else the AI
            already handled. Answer a gap once and it&apos;s folded into the
            knowledge base for the next parent.
          </div>

          {/* At-a-glance stats */}
          <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
            <StatChip label="Need attention" value={stats.attention} tone="amber" />
            <StatChip label="Auto-answered" value={stats.answered} tone="green" />
            <StatChip label="Resolved" value={stats.resolved} tone="indigo" />
          </div>

          {!loading && stats.attention === 0 && (
            <div style={{ marginTop: 12, fontSize: 13, color: "#227A47", fontWeight: 600 }}>
              ✓ You&apos;re all caught up — nothing needs you right now.
            </div>
          )}

          {/* Group-by control */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginTop: 18,
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: "12.5px", color: "#737685", fontWeight: 600, marginRight: 2 }}>
              Group by
            </span>
            {(Object.keys(GROUP_BY_LABELS) as GroupBy[]).map((g) => (
              <button
                key={g}
                onClick={() => setGroupBy(g)}
                style={{
                  padding: "6px 13px",
                  borderRadius: 999,
                  fontSize: "12.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                  transition: "all .15s",
                  border: `1px solid ${groupBy === g ? "#5463D6" : "#E3E8FF"}`,
                  background: groupBy === g ? "#5463D6" : "#FFFFFF",
                  color: groupBy === g ? "#FFFFFF" : "#5463D6",
                }}
              >
                {GROUP_BY_LABELS[g]}
              </button>
            ))}
          </div>

          {loading ? (
            <div style={{ padding: 28, fontSize: 14, color: "#737685" }}>
              Loading inbox…
            </div>
          ) : grouped.length === 0 ? (
            <div style={{ padding: 28, fontSize: 14, color: "#737685" }}>
              No questions yet.
            </div>
          ) : (
            grouped.map((g) => (
              <CollapsibleGroup
                key={g.id}
                group={g}
                collapsed={collapsed.has(g.id)}
                onToggle={() => toggleGroup(g.id)}
                onOpen={openDetail}
              />
            ))
          )}
        </>
      ) : (
        <InquiryDetail
          item={selected}
          replyText={replyText}
          setReplyText={setReplyText}
          proposal={proposal}
          conflict={conflict}
          stage={stage}
          resolvedCount={resolvedCount}
          busy={busy}
          err={err}
          onBack={back}
          onDraft={draft}
          onFold={fold}
          onMarkHandled={markHandled}
          onReplied={() => {
            onChanged?.();
            load();
          }}
          onDiscardProposal={() => {
            setProposal(null);
            setStage("idle");
          }}
        />
      )}
    </div>
  );
}

function InquiryDetail({
  item,
  replyText,
  setReplyText,
  proposal,
  conflict,
  stage,
  resolvedCount,
  busy,
  err,
  onBack,
  onDraft,
  onFold,
  onMarkHandled,
  onReplied,
  onDiscardProposal,
}: {
  item: InboxItem;
  replyText: string;
  setReplyText: (v: string) => void;
  proposal: Proposal | null;
  conflict: Change | null;
  stage: "idle" | "proposed" | "resolved";
  resolvedCount: number;
  busy: boolean;
  err: string | null;
  onBack: () => void;
  onDraft: () => void;
  onFold: (changes: Change[]) => void;
  onMarkHandled: () => void;
  onReplied: () => void;
  onDiscardProposal: () => void;
}) {
  const s = statusStyles[item.status];
  const sensitive = item.category ? SENSITIVE.has(item.category) : false;
  const actionable = item.status === "escalated" || item.status === "lowconf";

  // Conversation transcript + direct reply (private; never touches the graph).
  const [thread, setThread] = useState<Thread | null>(null);
  const [parentReply, setParentReply] = useState("");
  const [sending, setSending] = useState(false);
  const [replyErr, setReplyErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setThread(null);
    // Poll the open thread so the parent's new messages appear live.
    const load = () =>
      fetchThread(item.id)
        .then((t) => live && setThread(t))
        .catch(() => {});
    load();
    const poll = setInterval(load, 2500);
    return () => {
      live = false;
      clearInterval(poll);
    };
  }, [item.id]);

  const sendReply = async () => {
    const t = parentReply.trim();
    if (!t || sending) return;
    setSending(true);
    setReplyErr(null);
    try {
      await replyToParent(item.id, t);
      setParentReply("");
      const fresh = await fetchThread(item.id).catch(() => null);
      if (fresh) setThread(fresh);
      onReplied();
    } catch (e) {
      setReplyErr(e instanceof Error ? e.message : "Couldn't send reply.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <button
        onClick={onBack}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: "transparent",
          border: "none",
          color: "#5463D6",
          fontSize: 13,
          fontWeight: 700,
          cursor: "pointer",
          padding: 0,
          marginBottom: 16,
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m15 18-6-6 6-6" />
        </svg>
        Back to inbox
      </button>

      <div
        style={{
          background: "#FFFFFF",
          border: "1px solid #EBEFF4",
          borderRadius: 20,
          padding: 22,
          boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span
            style={{
              background: s.bg,
              color: s.color,
              padding: "5px 11px",
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {s.label}
          </span>
          {sensitive && (
            <span
              style={{
                background: "#FDEFF2",
                color: "#CF193A",
                padding: "5px 11px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
              }}
            >
              Sensitive · {item.category}
            </span>
          )}
          {item.group_count > 1 && (
            <span
              style={{
                background: "#FFF1DE",
                color: "#B5710A",
                padding: "5px 11px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 800,
              }}
            >
              {item.group_count} parents asked this
            </span>
          )}
        </div>

        <div style={{ fontSize: 19, fontWeight: 700, color: "#18181D", marginTop: 14 }}>
          {item.text}
        </div>
        <div style={{ fontSize: "13px", color: "#737685", marginTop: 6 }}>
          {item.who} · {timeAgo(item.created_at)}
        </div>

        {item.status === "resolved" && item.resolution_text && (
          <div
            style={{
              marginTop: 16,
              background: "#F7F9FB",
              borderRadius: 12,
              padding: "12px 14px",
              fontSize: 14,
              color: "#3E4252",
            }}
          >
            <b>Resolution:</b> {item.resolution_text}
          </div>
        )}
      </div>

      {/* Conversation transcript */}
      {thread && thread.messages.length > 0 && (
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
          <div style={{ fontSize: 15, fontWeight: 700, color: "#18181D" }}>
            Conversation
          </div>
          <div
            className="fd-scroll"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              marginTop: 14,
              maxHeight: 320,
              overflowY: "auto",
              paddingRight: 4,
            }}
          >
            {thread.messages.map((m) => (
              <TranscriptBubble key={m.id} m={m} />
            ))}
          </div>
        </div>
      )}

      {/* Reply directly to the parent (private — no graph write) */}
      {thread?.can_reply && (
        <div
          style={{
            marginTop: 18,
            background: "#FFFFFF",
            border: "1px solid #EBEFF4",
            borderRadius: 20,
            padding: 22,
            boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 700, color: "#18181D" }}>
            Reply to {item.who}
          </div>
          <div style={{ fontSize: "13px", color: "#5C5E6A", marginTop: 6, lineHeight: 1.5 }}>
            A private message in this parent&apos;s chat. It is{" "}
            <b>not</b> added to the knowledge base and the AI never sees it.
          </div>
          <textarea
            value={parentReply}
            onChange={(e) => setParentReply(e.target.value)}
            placeholder="Write a direct reply to this parent…"
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
              minHeight: 76,
              resize: "none",
            }}
          />
          {replyErr && (
            <div style={{ marginTop: 10, fontSize: 13, color: "#CF193A", fontWeight: 600 }}>
              {replyErr}
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
            <button onClick={sendReply} disabled={sending} style={primaryBtn(sending)}>
              {sending ? "Sending…" : "Send reply"}
            </button>
          </div>
        </div>
      )}
      {thread && !thread.can_reply && (
        <div
          style={{
            marginTop: 18,
            background: "#F7F9FB",
            border: "1px dashed #D9DFEA",
            borderRadius: 14,
            padding: "14px 16px",
            fontSize: 13,
            color: "#737685",
          }}
        >
          No parent account is linked to this inquiry, so there&apos;s no chat to
          reply into.
        </div>
      )}

      {/* Teach & fold */}
      {actionable && stage !== "resolved" && (
        <div
          style={{
            marginTop: 18,
            background: "#FFFFFF",
            border: "1px solid #EBEFF4",
            borderRadius: 20,
            padding: 22,
            boxShadow: "0 8px 24px -18px rgba(30,37,73,.3)",
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 700, color: "#18181D" }}>
            Answer &amp; teach Sunnyside
          </div>
          <div style={{ fontSize: "13px", color: "#5C5E6A", marginTop: 6, lineHeight: 1.5 }}>
            {sensitive
              ? "Reply for your records. Sensitive topics still escalate to staff even after you add a note."
              : "Write the answer in plain language. I'll fold it into the knowledge base so the next parent who asks gets it instantly and grounded."}
          </div>

          <textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder={
              sensitive
                ? "e.g. Called the family back; advised per our illness policy."
                : "e.g. We offer a 3-day part-time schedule for $950/mo, Mon/Wed/Fri."
            }
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
              minHeight: 84,
              resize: "none",
            }}
          />

          {err && (
            <div style={{ marginTop: 10, fontSize: 13, color: "#CF193A", fontWeight: 600 }}>
              {err}
            </div>
          )}

          {stage !== "proposed" && (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
                marginTop: 14,
              }}
            >
              {sensitive && (
                <button onClick={onMarkHandled} disabled={busy} style={ghostBtn}>
                  {busy ? "Saving…" : "Mark handled (no change)"}
                </button>
              )}
              <button onClick={onDraft} disabled={busy} style={primaryBtn(busy)}>
                {busy ? "Drafting…" : "Draft update"}
              </button>
            </div>
          )}

          {/* Proposed diff + (optional) conflict resolution */}
          {stage === "proposed" && proposal && (
            <div style={{ marginTop: 16 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: ".04em",
                  textTransform: "uppercase",
                  color: "#737685",
                }}
              >
                {proposal.summary}
              </div>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                {proposal.changes.map((c, i) => (
                  <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {c.old_value && (
                      <div
                        style={{
                          display: "flex",
                          gap: 10,
                          background: "#FDEFF2",
                          borderRadius: 10,
                          padding: "11px 13px",
                        }}
                      >
                        <span style={{ color: "#CF193A", fontWeight: 800 }}>–</span>
                        <span
                          style={{
                            fontSize: 14,
                            color: "#9497A6",
                            textDecoration: "line-through",
                          }}
                        >
                          {c.name} · {c.field}: {c.old_value}
                        </span>
                      </div>
                    )}
                    <div
                      style={{
                        display: "flex",
                        gap: 10,
                        background: "#E7F7EE",
                        borderRadius: 10,
                        padding: "11px 13px",
                      }}
                    >
                      <span style={{ color: "#227A47", fontWeight: 800 }}>+</span>
                      <span style={{ fontSize: 14, color: "#18181D", fontWeight: 600 }}>
                        {c.name} · {c.field}: {c.new_value}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {conflict ? (
                <div
                  style={{
                    marginTop: 14,
                    border: "1px solid #F6D9A6",
                    background: "#FFF9EF",
                    borderRadius: 14,
                    padding: 15,
                  }}
                >
                  <div style={{ fontSize: "13.5px", fontWeight: 700, color: "#8A5A00" }}>
                    This conflicts with a fact on file ({conflict.old_value}). Which
                    should parents see?
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      gap: 10,
                      marginTop: 14,
                    }}
                  >
                    <button onClick={onMarkHandled} disabled={busy} style={ghostBtn}>
                      Keep {conflict.old_value}
                    </button>
                    <button
                      onClick={() => onFold(proposal.changes)}
                      disabled={busy}
                      style={primaryBtn(busy)}
                    >
                      {busy ? "Publishing…" : `Use “${conflict.new_value}”`}
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: 10,
                    marginTop: 16,
                  }}
                >
                  <button onClick={onDiscardProposal} disabled={busy} style={ghostBtn}>
                    Rewrite
                  </button>
                  <button
                    onClick={() => onFold(proposal.changes)}
                    disabled={busy}
                    style={primaryBtn(busy)}
                  >
                    {busy ? "Publishing…" : "Confirm & fold in"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {stage === "resolved" && (
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
            <div style={{ fontSize: "14.5px", fontWeight: 700, color: "#1A6B3D" }}>
              Resolved{resolvedCount > 1 ? ` ${resolvedCount} grouped questions` : ""} —
              the next parent who asks gets it instantly.
            </div>
            <div style={{ fontSize: "12.5px", color: "#3E8259", marginTop: 2 }}>
              Logged to the changelog and folded into the knowledge graph.
            </div>
          </div>
          <button onClick={onBack} style={{ ...ghostBtn, marginLeft: "auto" }}>
            Back to inbox
          </button>
        </div>
      )}
    </div>
  );
}
