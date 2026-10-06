import { NextRequest, NextResponse } from "next/server";
import { validateApiKey } from "@/lib/auth";
import { extractProductsFromImage, PRIMARY_MODEL_NAME, REVIEW_MODEL_NAME } from "@/lib/gemini";

export const maxDuration = 60; // Allow Vercel 60s timeout for vision LLMs

export async function POST(req: NextRequest) {
  const auth = validateApiKey(req);
  if (!auth.authorized) {
    return NextResponse.json({ error: auth.error }, { status: 401 });
  }

  try {
    const formData = await req.formData();
    const files = formData.getAll("files") as File[];
    const modelName = (formData.get("modelName") as string) || PRIMARY_MODEL_NAME;
    const reviewModel = (formData.get("reviewModel") as string) || REVIEW_MODEL_NAME;
    const temperature = parseFloat((formData.get("temperature") as string) || "0.0");

    if (!files || files.length === 0) {
      return NextResponse.json({ error: "No image files provided" }, { status: 400 });
    }

    const allRows = [];
    const allRaw = [];
    const errors = [];
    let rereadCount = 0;
    let needsReviewCount = 0;

    for (const file of files) {
      try {
        const buffer = Buffer.from(await file.arrayBuffer());
        const mimeType = file.type || "image/jpeg";
        const result = await extractProductsFromImage({
          filename: file.name,
          imageBytes: buffer,
          mimeType,
          modelName,
          reviewModel,
          temperature,
        });

        allRows.push(...result.rows);
        allRaw.push({
          source_file: file.name,
          ...result.rawExtraction,
          cross_check: result.crossCheck,
          attempts: result.attempts,
        });
        if (result.attempts > 1) rereadCount++;
        if (result.needsReview) needsReviewCount++;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`${file.name}: ${msg}`);
      }
    }

    return NextResponse.json({
      rows: allRows,
      raw: allRaw,
      errors,
      metrics: {
        total_files: files.length,
        total_rows: allRows.length,
        reread_count: rereadCount,
        needs_review_count: needsReviewCount,
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
