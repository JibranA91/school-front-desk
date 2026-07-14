import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

// Persist the signed-in user's color-scheme preference. The user id is taken
// from the session (never the client), so a user can only change their own.
export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { theme } = await req.json().catch(() => ({ theme: "light" }));
  try {
    const upstream = await fetch(
      `${API_BASE_URL}/me/theme?user_id=${encodeURIComponent(session.user.id)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: theme === "dark" ? "dark" : "light" }),
        cache: "no-store",
      },
    );
    if (!upstream.ok) {
      return NextResponse.json({ error: "theme update failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
