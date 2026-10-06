import { NextRequest, NextResponse } from "next/server";
import { fetchRows, upsertRows } from "@/lib/db";
import { ExtractedRow } from "@/types/schema";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const search = searchParams.get("search") || undefined;
  const supplier = searchParams.get("supplier") || undefined;
  const reviewParam = searchParams.get("needs_review");
  const needs_review = reviewParam === "true" ? true : reviewParam === "false" ? false : null;
  const limit = parseInt(searchParams.get("limit") || "100", 10);
  const offset = parseInt(searchParams.get("offset") || "0", 10);

  const t0 = performance.now();
  const result = await fetchRows({ search, supplier, needs_review, limit, offset });
  const latencyMs = performance.now() - t0;

  return NextResponse.json({
    rows: result.rows,
    total: result.total,
    latency_ms: Math.round(latencyMs * 10) / 10,
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const rows = body.rows as ExtractedRow[];
    if (!rows || !Array.isArray(rows)) {
      return NextResponse.json({ error: "Invalid rows payload" }, { status: 400 });
    }
    const result = await upsertRows(rows);
    return NextResponse.json({
      success: true,
      inserted: result.inserted,
      updated: result.updated,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
