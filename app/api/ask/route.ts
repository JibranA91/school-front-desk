import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

// Parent chat → agent. Runs server-side so the API URL stays private and the
// authenticated parent's identity is attached (never trusted from the client).
export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let question: unknown;
  let sessionId: unknown;
  try {
    ({ question, session_id: sessionId } = await req.json());
  } catch {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  if (typeof question !== "string" || !question.trim()) {
    return NextResponse.json({ error: "question required" }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        asker_id: session.user.id ?? null,
        session_id: typeof sessionId === "string" ? sessionId : null,
      }),
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "front desk unavailable" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "front desk unreachable" }, { status: 502 });
  }
}
