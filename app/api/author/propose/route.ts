import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

export async function POST(req: Request) {
  const session = await auth();
  if (session?.user?.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const { instruction } = await req.json();
  if (typeof instruction !== "string" || !instruction.trim()) {
    return NextResponse.json({ error: "instruction required" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${API_BASE_URL}/author/propose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction }),
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "propose failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
