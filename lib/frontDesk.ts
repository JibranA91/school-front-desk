// Front-desk types + client calls.
// Parent chat now calls the real backend (`/api/ask` → FastAPI → agent).
// The operator seed data below is still mock — wired to the DB in a later step.

export type MsgType =
  | "user"
  | "assistant-text"
  | "confident"
  | "escalation"
  | "lunch";

export interface Msg {
  id: number;
  type: MsgType;
  text?: string;
  answer?: string;
  citation?: string;
  source?: string;
  menu?: string[];
}

export const chips: { label: string; q: string }[] = [
  { label: "What are your hours?", q: "What are your hours?" },
  { label: "Infant tuition?", q: "How much is infant tuition?" },
  { label: "Is lunch provided today?", q: "Is lunch provided today?" },
  { label: "My child has a fever", q: "My child has a fever" },
];

/** The structured answer returned by the agent (via /api/ask). */
export interface AskResult {
  kind: MsgType;
  answer: string;
  citation?: string | null;
  source?: string | null;
  menu?: string[] | null;
  category?: string | null;
  needs_escalation?: boolean;
}

export async function askFrontDesk(question: string): Promise<AskResult> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return res.json();
}

/** Map an AskResult into a chat Msg the UI can render. */
export function resultToMessage(id: number, r: AskResult): Msg {
  if (r.kind === "assistant-text") {
    return { id, type: "assistant-text", text: r.answer };
  }
  return {
    id,
    type: r.kind,
    answer: r.answer,
    citation: r.citation ?? undefined,
    source: r.source ?? undefined,
    menu: r.menu ?? undefined,
  };
}

// ---- Operator: chat-to-author (wired to the /author agent) ----

export interface Change {
  action: "add" | "update";
  entity_id: string;
  entity_type: string;
  name: string;
  field: string;
  old_value: string | null;
  new_value: string;
  is_conflict: boolean;
  source: string | null;
}

export interface Proposal {
  summary: string;
  changes: Change[];
  has_conflict: boolean;
}

export async function proposeChange(instruction: string): Promise<Proposal> {
  const res = await fetch("/api/author/propose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) throw new Error(`propose failed: ${res.status}`);
  return res.json();
}

export async function applyChange(
  changes: Change[],
  summary: string,
  acceptConflicts: boolean
): Promise<{ applied: string[] }> {
  const res = await fetch("/api/author/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ changes, summary, accept_conflicts: acceptConflicts }),
  });
  if (!res.ok) throw new Error(`apply failed: ${res.status}`);
  return res.json();
}

// ---- Operator: handbook ingestion (upload a PDF → typed graph entities) ----

export interface IngestReport {
  source: string;
  mode: "bedrock" | "heuristic";
  pages: number;
  chunks: number;
  created: number;
  by_type: Record<string, number>;
  replaced?: number;
}

export async function importHandbook(
  file: File,
  label?: string
): Promise<IngestReport> {
  const body = new FormData();
  body.append("file", file, file.name);
  if (label) body.append("label", label);
  const res = await fetch("/api/ingest", { method: "POST", body });
  if (!res.ok) {
    const msg = await res.json().catch(() => ({}));
    throw new Error(msg?.error ?? `ingest failed: ${res.status}`);
  }
  return res.json();
}

// ---- Operator: knowledge-graph visualization ----

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  source: string | null;
  handbook: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  rel: string;
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function fetchGraph(): Promise<KnowledgeGraph> {
  const res = await fetch("/api/graph", { cache: "no-store" });
  if (!res.ok) throw new Error(`graph failed: ${res.status}`);
  return res.json();
}

export async function fetchChangelog(): Promise<ChangelogEntry[]> {
  const res = await fetch("/api/changelog");
  if (!res.ok) throw new Error(`changelog failed: ${res.status}`);
  return res.json();
}

// ---- Operator seed data (inbox still mock; changelog seeds the DB) ----

export type InboxStatus = "answered" | "escalated" | "lowconf" | "resolved";

export interface InboxItem {
  id: string;
  text: string;
  status: InboxStatus;
  category: string | null;
  confidence: number | null;
  who: string;
  group_key: string | null;
  group_count: number;
  resolution_text: string | null;
  created_at: string | null;
}

export const statusStyles: Record<
  InboxStatus,
  { bg: string; color: string; label: string }
> = {
  answered: { bg: "#E7F7EE", color: "#227A47", label: "Answered" },
  escalated: { bg: "#FFF1DE", color: "#B5710A", label: "Escalated" },
  lowconf: { bg: "#FFF7DB", color: "#9A7B12", label: "Low confidence" },
  resolved: { bg: "#EEF1FF", color: "#4B57B8", label: "Resolved" },
};

export async function fetchInbox(): Promise<InboxItem[]> {
  const res = await fetch("/api/inbox", { cache: "no-store" });
  if (!res.ok) throw new Error(`inbox failed: ${res.status}`);
  return res.json();
}

/** Close the learning loop: fold the operator's answer into the graph and mark
 *  the inquiry (and open siblings in its group) resolved. */
export async function resolveInquiry(
  id: string,
  payload: {
    changes?: Change[];
    summary?: string;
    acceptConflicts?: boolean;
    resolutionText?: string;
    resolveGroup?: boolean;
  }
): Promise<{ resolved: string[]; applied: string[] }> {
  const res = await fetch(`/api/inbox/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      changes: payload.changes ?? [],
      summary: payload.summary ?? null,
      accept_conflicts: payload.acceptConflicts ?? true,
      resolution_text: payload.resolutionText ?? null,
      resolve_group: payload.resolveGroup ?? true,
    }),
  });
  if (!res.ok) {
    const msg = await res.json().catch(() => ({}));
    throw new Error(msg?.error ?? `resolve failed: ${res.status}`);
  }
  return res.json();
}

export const suggestions: { label: string; text: string }[] = [
  {
    label: "Closed the Friday after Thanksgiving",
    text: "We're now closed the Friday after Thanksgiving (Nov 28).",
  },
  { label: "We now open at 6:30 AM", text: "We now open at 6:30 AM on weekdays." },
];

export interface ChangelogEntry {
  who: string;
  when: string;
  what: string;
  before?: string;
  after?: string;
  isDiff: boolean;
  initials: string;
  color: string;
}

export const changelog: ChangelogEntry[] = [
  {
    who: "Maria Chen",
    when: "Today · 9:14 AM",
    what: "Updated Today's Menu",
    before: "PB&J, carrots, milk",
    after: "Turkey & cheese, apple slices, milk",
    isDiff: true,
    initials: "MC",
    color: "#5463D6",
  },
  {
    who: "AI Front Desk",
    when: "Today · 9:02 AM",
    what: "Escalated a fever question to the Toddler Room staff",
    isDiff: false,
    initials: "AI",
    color: "#29B9BB",
  },
  {
    who: "Auto-sync",
    when: "Oct 28 · 6:00 AM",
    what: "Adjusted infant tuition",
    before: "$1,550 / mo",
    after: "$1,600 / mo",
    isDiff: true,
    initials: "SY",
    color: "#737685",
  },
  {
    who: "Maria Chen",
    when: "Oct 15 · 10:20 AM",
    what: "Confirmed illness policy — fever 100.4°F, stay home 24 h fever-free",
    isDiff: false,
    initials: "MC",
    color: "#5463D6",
  },
];
