import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

// The parent's escalation/notifications feed. parent_id comes from the session.
export async function GET() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  try {
    const upstream = await fetch(
      `${API_BASE_URL}/my/updates?parent_id=${encodeURIComponent(session.user.id)}`,
      { cache: "no-store" },
    );
    if (!upstream.ok) {
      return NextResponse.json({ error: "updates failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
