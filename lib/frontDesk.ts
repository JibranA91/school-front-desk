// Mock front-desk logic + seed data.
// NOTE: this is the demo stand-in for the real agents. The `answerFor` keyword
// router here will be replaced by `POST /api/ask` (Bedrock) per .plans/spec.md;
// the operator seed data will come from the server-side knowledge graph.

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

export const seedMessages: Msg[] = [
  { id: 2, type: "user", text: "What are your hours?" },
  {
    id: 3,
    type: "confident",
    answer:
      "We're open Monday through Friday, 7:00 AM to 6:00 PM. We're closed on weekends and major holidays.",
    citation: "per our Hours & Schedule",
    source:
      "Hours & Schedule · Open Mon–Fri, 7:00 AM–6:00 PM. Closed weekends & major holidays. Reviewed by Maria Chen on Oct 15, 2025.",
  },
  { id: 4, type: "user", text: "My child has a fever" },
  {
    id: 5,
    type: "escalation",
    answer:
      "I want to make sure you get the right guidance on this — I've flagged it for our staff, who'll reach out shortly. While you wait: our policy asks that children with a fever of 100.4°F or higher stay home until they've been fever-free for 24 hours.",
  },
  { id: 6, type: "user", text: "Is lunch provided today?" },
  {
    id: 7,
    type: "lunch",
    answer:
      "Yes — a fresh lunch is served every day and it's included in tuition. Here's what's on today's tray:",
    menu: ["Turkey & cheese sandwich", "Crisp apple slices", "Whole milk"],
    citation: "per Today’s Menu",
    source: "Today's Menu · Synced from the kitchen at 6:30 AM today.",
  },
];

export function answerFor(text: string): Omit<Msg, "id"> {
  const t = text.toLowerCase();
  if (t.includes("fever") || t.includes("sick") || t.includes("temperature")) {
    return {
      type: "escalation",
      answer:
        "I want to make sure you get the right guidance on this — I've flagged it for our staff, who'll reach out shortly. While you wait: our policy asks that children with a fever of 100.4°F or higher stay home until they've been fever-free for 24 hours.",
    };
  }
  if (
    t.includes("tuition") ||
    t.includes("cost") ||
    t.includes("price") ||
    t.includes("how much")
  ) {
    return {
      type: "confident",
      answer:
        "Infant tuition is $1,600 per month. That includes daily meals, diapers, and wipes — there are no separate supply fees.",
      citation: "per Tuition & Fees",
      source:
        "Tuition & Fees · Infant $1,600/mo, includes meals & supplies. Reviewed by Maria Chen on Oct 15, 2025.",
    };
  }
  if (
    t.includes("lunch") ||
    t.includes("menu") ||
    t.includes("food") ||
    t.includes("eat")
  ) {
    return {
      type: "lunch",
      answer:
        "Yes — a fresh lunch is served every day and it's included in tuition. Here's what's on today's tray:",
      menu: ["Turkey & cheese sandwich", "Crisp apple slices", "Whole milk"],
      citation: "per Today’s Menu",
      source: "Today's Menu · Synced from the kitchen at 6:30 AM today.",
    };
  }
  if (
    t.includes("hour") ||
    t.includes("open") ||
    t.includes("close") ||
    t.includes("time")
  ) {
    return {
      type: "confident",
      answer:
        "We're open Monday through Friday, 7:00 AM to 6:00 PM. We're closed on weekends and major holidays.",
      citation: "per our Hours & Schedule",
      source:
        "Hours & Schedule · Open Mon–Fri, 7:00 AM–6:00 PM. Closed weekends & major holidays. Reviewed Oct 15, 2025.",
    };
  }
  if (t.includes("tour") || t.includes("visit")) {
    return {
      type: "confident",
      answer:
        "We'd love to show you around! Tours run Tuesday and Thursday mornings, and you can book one online in about a minute.",
      citation: "per Visits & Tours",
      source: "Visits & Tours · Offered Tue/Thu mornings, booked online.",
    };
  }
  return {
    type: "assistant-text",
    text: "That's a great question — I want to be sure I give you the right answer, so I've passed it to our staff. Someone from Sunnyside will follow up with you shortly.",
  };
}

// ---- Operator seed data ----

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
