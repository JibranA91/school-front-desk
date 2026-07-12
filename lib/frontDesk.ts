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

// ---- Operator seed data (still mock; wired to the DB later) ----

export type InboxStatus = "answered" | "escalated" | "lowconf";

export interface InboxItem {
  q: string;
  who: string;
  time: string;
  status: InboxStatus;
}

export const statusStyles: Record<
  InboxStatus,
  { bg: string; color: string; label: string }
> = {
  answered: { bg: "#E7F7EE", color: "#227A47", label: "Answered" },
  escalated: { bg: "#FFF1DE", color: "#B5710A", label: "Escalated" },
  lowconf: { bg: "#FFF7DB", color: "#9A7B12", label: "Low confidence" },
};

export const inbox: InboxItem[] = [
  {
    q: "My child has a fever — should I keep her home?",
    who: "Parent of Ava · Toddler Room",
    time: "2 min ago",
    status: "escalated",
  },
  {
    q: "Do you offer a 3-day / part-time schedule?",
    who: "Prospective family",
    time: "14 min ago",
    status: "lowconf",
  },
  {
    q: "What are your hours?",
    who: "Parent of Noah",
    time: "26 min ago",
    status: "answered",
  },
  {
    q: "How much is infant tuition?",
    who: "Prospective family",
    time: "1 hr ago",
    status: "answered",
  },
  {
    q: "Are you closed on Veterans Day?",
    who: "Parent of Liam",
    time: "3 hr ago",
    status: "answered",
  },
  {
    q: "Can I book a tour for next Tuesday?",
    who: "Prospective family",
    time: "Yesterday",
    status: "answered",
  },
];

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
