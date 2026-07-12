import { NextResponse } from "next/server";

import { auth } from "@/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8001";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (session?.user?.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const { id } = await params;
  try {
    const upstream = await fetch(`${API_BASE_URL}/inbox/${id}/thread`, {
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "thread failed" }, { status: 502 });
    }
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json({ error: "unreachable" }, { status: 502 });
  }
}
