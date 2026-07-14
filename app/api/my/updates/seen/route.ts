import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

// Mark the parent's Updates feed as read. parent_id comes from the session.
export async function POST() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  try {
    const upstream = await fetch(
      `${API_BASE_URL}/my/updates/seen?parent_id=${encodeURIComponent(session.user.id)}`,
      { method: "POST" },
    );
    return NextResponse.json(await upstream.json().catch(() => ({ ok: true })));
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
