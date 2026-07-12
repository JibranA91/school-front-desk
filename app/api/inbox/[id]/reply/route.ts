import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (session?.user?.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  if (typeof body.text !== "string" || !body.text.trim()) {
    return NextResponse.json({ error: "text required" }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/inbox/${id}/reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: body.text,
        actor: session.user.name ?? "Operator",
        actor_user_id: session.user.id ?? null,
      }),
    });
    const data = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.detail ?? "reply failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
