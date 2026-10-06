import { GoogleGenAI } from "@google/genai";
import crypto from "crypto";
import {
  CrossCheckResult,
  CrossCheckResultSchema,
  ExtractedRow,
  ImageExtraction,
  ImageExtractionSchema,
} from "../types/schema";

export const PRIMARY_MODEL_NAME = "gemini-3.5-flash-lite";
export const PRIMARY_MODEL_LABEL = "Gemini 3.5 Flash Lite";
export const REVIEW_MODEL_NAME = "gemma-4-26b";
export const REVIEW_MODEL_LABEL = "Gemma 4 26B";

const STRICT_EXTRACTION_SYSTEM_PROMPT = `You are a rigorous, high-precision OCR and structured data extraction engine specialized in commercial product labels, retail receipts, packing slips, and invoices. You strictly extract factual data visible in the image into structured JSON matching the provided schema. Never fabricate, guess, or extrapolate missing values. Ensure complete and accurate extraction.`;

const STRICT_EXTRACTION_PROMPT = `Analyze the attached image and extract all distinct product line items.
For every line item, strictly extract:
1. 'product_name': The full descriptive name of the item (do not omit).
2. 'product_code': The SKU, barcode, article number, or reference code if visible.
3. 'quantity': The numerical quantity purchased or listed (must be a positive number).
4. 'unit': The unit of measure (e.g., pcs, box, kg, pack, can, bottle).
5. 'unit_price': The price per single unit (numeric, without currency symbols).
6. 'total_price': The line total amount (numeric, without currency symbols).
7. 'currency': The ISO currency code (e.g., VND, USD, EUR, etc., or UNKNOWN).
8. 'notes': Any specific attributes like size, color, or batch number.
9. 'confidence': Your confidence score between 0.0 and 1.0.

Also extract document-level metadata:
- 'supplier': Business name or seller.
- 'invoice_number': Receipt, bill, or invoice identifier.
- 'invoice_date': Document date string.
- 'staff_name': Cashier, operator, or sales representative if present.
- 'total_amount': Grand total amount on document if present.

Ensure maximum completeness. Return valid JSON only.`;

const STRICT_REVIEW_SYSTEM_PROMPT = `You are an automated quality assurance auditor for commercial product extraction. Your role is to cross-check extracted product data for completeness, validity, and consistency.`;

const STRICT_REVIEW_PROMPT_TEMPLATE = `Review the following extracted invoice/product data for completeness and quality:

{extracted_json}

Audit criteria:
1. Completeness: Every line item MUST have a non-empty, descriptive product name, a positive quantity (> 0), and a unit.
2. Identification: Product code / SKU should be extracted if visible.
3. Math consistency: If unit_price and total_price are both present, check if quantity * unit_price is approximately total_price.
4. Document completeness: Check if supplier and invoice_number are identified.

Return strict JSON matching the schema with fields:
- 'is_complete': boolean (true if all items have complete product name, quantity > 0, and no critical omissions; false otherwise)
- 'missing_fields': list of strings identifying missing fields
- 'issues': list of strings describing any errors or incomplete details
- 'recommended_action': string ('approved' if complete, 'reread' if critical fields are missing, 'needs_review' if persistent issues)`;

export function getClient(): GoogleGenAI {
  const apiKey = process.env.GEMINI_API_KEY || "";
  if (!apiKey) {
    throw new Error("Missing GEMINI_API_KEY environment variable.");
  }
  return new GoogleGenAI({ apiKey });
}

export async function listVisionModels(): Promise<{ name: string; displayName: string }[]> {
  try {
    const ai = getClient();
    const pager = await ai.models.list({ config: { pageSize: 200 } });
    const models: { name: string; displayName: string }[] = [];
    const seen = new Set<string>();

    for await (const m of pager) {
      const rawName = m.name || "";
      const shortName = rawName.split("/").pop() || "";
      const lower = shortName.toLowerCase();
      if (!shortName || seen.has(shortName)) continue;
      if (lower.includes("embedding") || lower.includes("embed") || lower.includes("aqa")) continue;

      seen.add(shortName);
      models.push({
        name: shortName,
        displayName: m.displayName || shortName,
      });
    }

    if (!seen.has(PRIMARY_MODEL_NAME)) {
      models.unshift({
        name: PRIMARY_MODEL_NAME,
        displayName: PRIMARY_MODEL_LABEL,
      });
    }
    return models;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.warn("Could not list live models, using default vision set:", message);
    return [
      { name: PRIMARY_MODEL_NAME, displayName: PRIMARY_MODEL_LABEL },
      { name: "gemini-2.5-flash", displayName: "Gemini 2.5 Flash" },
      { name: "gemini-2.5-flash-lite", displayName: "Gemini 2.5 Flash Lite" },
      { name: "gemini-2.0-flash", displayName: "Gemini 2.0 Flash" },
      { name: "gemini-2.5-pro", displayName: "Gemini 2.5 Pro" },
    ];
  }
}

export function localCrossCheck(extraction: ImageExtraction): CrossCheckResult {
  const missing: string[] = [];
  const issues: string[] = [];

  if (!extraction.items || extraction.items.length === 0) {
    return {
      is_complete: false,
      missing_fields: ["items"],
      issues: ["No product line items found in the extraction."],
      recommended_action: "reread",
    };
  }

  extraction.items.forEach((item, idx) => {
    const prefix = `Line ${idx + 1}`;
    if (!item.product_name || item.product_name.trim().length < 2) {
      missing.push(`${prefix}: product_name`);
      issues.push(`${prefix} is missing a descriptive product name.`);
    }
    if (item.quantity <= 0) {
      missing.push(`${prefix}: quantity`);
      issues.push(`${prefix} quantity must be greater than zero.`);
    }
    if (!item.unit) {
      missing.push(`${prefix}: unit`);
      issues.push(`${prefix} (${item.product_name || "item"}) is missing a unit.`);
    }
    if (item.unit_price && item.total_price && item.quantity > 0) {
      const expected = item.quantity * item.unit_price;
      const diff = Math.abs(expected - item.total_price);
      if (diff > Math.max(1, 0.05 * item.total_price)) {
        issues.push(`${prefix} math mismatch: ${item.quantity} * ${item.unit_price} != ${item.total_price}`);
      }
    }
  });

  const isComplete = missing.length === 0;
  return {
    is_complete: isComplete,
    missing_fields: missing,
    issues,
    recommended_action: isComplete ? "approved" : "reread",
  };
}

export async function crossCheckWithGemma(
  ai: GoogleGenAI,
  reviewModel: string,
  extraction: ImageExtraction
): Promise<CrossCheckResult> {
  try {
    const prompt = STRICT_REVIEW_PROMPT_TEMPLATE.replace(
      "{extracted_json}",
      JSON.stringify(extraction, null, 2)
    );

    const response = await ai.models.generateContent({
      model: reviewModel,
      contents: [prompt],
      config: {
        systemInstruction: STRICT_REVIEW_SYSTEM_PROMPT,
        temperature: 0.0,
        responseMimeType: "application/json",
      },
    });

    const text = response.text || "";
    if (text) {
      const parsed = JSON.parse(text);
      return CrossCheckResultSchema.parse(parsed);
    }
  } catch {
    // Fall back gracefully to local deterministic check
  }
  return localCrossCheck(extraction);
}

export async function extractProductsFromImage(params: {
  filename: string;
  imageBytes: Buffer;
  mimeType: string;
  modelName: string;
  reviewModel: string;
  temperature?: number;
}): Promise<{
  rows: ExtractedRow[];
  rawExtraction: ImageExtraction;
  crossCheck: CrossCheckResult;
  attempts: number;
  needsReview: boolean;
}> {
  const ai = getClient();
  const hash = crypto.createHash("sha256").update(params.imageBytes).digest("hex");
  const base64Data = params.imageBytes.toString("base64");

  let attempts = 1;

  // Pass 1: Primary extraction
  const response = await ai.models.generateContent({
    model: params.modelName,
    contents: [
      STRICT_EXTRACTION_PROMPT,
      {
        inlineData: {
          mimeType: params.mimeType,
          data: base64Data,
        },
      },
    ],
    config: {
      systemInstruction: STRICT_EXTRACTION_SYSTEM_PROMPT,
      temperature: params.temperature ?? 0.0,
      responseMimeType: "application/json",
    },
  });

  const text = response.text || "{}";
  let extraction = ImageExtractionSchema.parse(JSON.parse(text));
  let crossCheck = await crossCheckWithGemma(ai, params.reviewModel, extraction);

  // Pass 2: Re-read if incomplete
  if (!crossCheck.is_complete) {
    attempts = 2;
    try {
      const rereadPrompt = `CRITICAL SECOND-PASS INSPECTION: Initial extraction was incomplete. Deficiencies: ${crossCheck.issues.join("; ")}. Please re-examine the image carefully and extract all product lines with full name, SKU, quantity, unit, and price.`;
      const secondResp = await ai.models.generateContent({
        model: params.modelName,
        contents: [
          rereadPrompt,
          {
            inlineData: {
              mimeType: params.mimeType,
              data: base64Data,
            },
          },
        ],
        config: {
          systemInstruction: STRICT_EXTRACTION_SYSTEM_PROMPT,
          temperature: params.temperature ?? 0.0,
          responseMimeType: "application/json",
        },
      });
      const secondText = secondResp.text || "{}";
      const secondExtraction = ImageExtractionSchema.parse(JSON.parse(secondText));
      const secondCheck = await crossCheckWithGemma(ai, params.reviewModel, secondExtraction);
      extraction = secondExtraction;
      crossCheck = secondCheck;
    } catch (e: unknown) {
      console.warn("Second-pass reread encountered an error:", e);
    }
  }

  const needsReview = !crossCheck.is_complete;
  const reviewNotes = crossCheck.issues.join("; ");
  const extractedAt = new Date().toISOString();

  const rows: ExtractedRow[] = extraction.items.map((item) => ({
    source_file: params.filename,
    image_hash: hash,
    model_name: params.modelName,
    supplier: extraction.supplier,
    invoice_number: extraction.invoice_number,
    invoice_date: extraction.invoice_date,
    product_name: item.product_name,
    product_code: item.product_code,
    quantity: item.quantity,
    unit: item.unit,
    unit_price: item.unit_price ?? null,
    total_price: item.total_price ?? null,
    currency: item.currency !== "UNKNOWN" ? item.currency : extraction.currency,
    notes: item.notes,
    confidence: item.confidence || extraction.confidence,
    needs_review: needsReview,
    review_notes: reviewNotes,
    extraction_attempts: attempts,
    cross_check_model: params.reviewModel,
    extracted_at: extractedAt,
  }));

  return {
    rows,
    rawExtraction: extraction,
    crossCheck,
    attempts,
    needsReview,
  };
}
