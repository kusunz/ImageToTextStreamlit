import { NextResponse } from "next/server";
import { listVisionModels } from "@/lib/gemini";

export async function GET() {
  try {
    const models = await listVisionModels();
    return NextResponse.json({ models });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
