import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

// Start a knowledge-hygiene scan. Operator-only. Returns a job_id to poll.
export async function POST(req: Request) {
  const session = await auth();
  if (session?.user?.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const { mode } = await req.json().catch(() => ({ mode: "quick" }));
  try {
    const upstream = await fetch(`${API_BASE_URL}/clean/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: mode === "deep" ? "deep" : "quick" }),
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "scan failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
