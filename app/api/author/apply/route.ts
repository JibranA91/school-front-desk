import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

export async function POST(req: Request) {
  const session = await auth();
  if (session?.user?.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const { changes, summary, accept_conflicts } = await req.json();
  if (!Array.isArray(changes)) {
    return NextResponse.json({ error: "changes required" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${API_BASE_URL}/author/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        changes,
        summary: summary ?? null,
        accept_conflicts: accept_conflicts ?? true,
        actor: session.user.name ?? "Operator",
        actor_user_id: session.user.id ?? null,
      }),
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "apply failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
