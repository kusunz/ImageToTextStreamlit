import { z } from "zod";

export const CurrencyCodeSchema = z.enum([
  "VND",
  "USD",
  "EUR",
  "JPY",
  "KRW",
  "CNY",
  "THB",
  "UNKNOWN",
]);
export type CurrencyCode = z.infer<typeof CurrencyCodeSchema>;

export const ProductItemSchema = z.object({
  product_name: z.string().default("").transform((s) => s.trim()),
  product_code: z.string().default("").transform((s) => s.trim()),
  quantity: z.coerce.number().default(0),
  unit: z.string().default("").transform((s) => s.trim()),
  unit_price: z.coerce.number().nullable().optional(),
  total_price: z.coerce.number().nullable().optional(),
  currency: CurrencyCodeSchema.default("UNKNOWN"),
  notes: z.string().default("").transform((s) => s.trim()),
  confidence: z.coerce.number().min(0).max(1).default(0),
});
export type ProductItem = z.infer<typeof ProductItemSchema>;

export const ImageExtractionSchema = z.object({
  supplier: z.string().default("").transform((s) => s.trim()),
  invoice_number: z.string().default("").transform((s) => s.trim()),
  invoice_date: z.string().default("").transform((s) => s.trim()),
  staff_name: z.string().default("").transform((s) => s.trim()),
  total_amount: z.coerce.number().nullable().optional(),
  currency: CurrencyCodeSchema.default("UNKNOWN"),
  items: z.array(ProductItemSchema).default([]),
  confidence: z.coerce.number().min(0).max(1).default(0),
});
export type ImageExtraction = z.infer<typeof ImageExtractionSchema>;

export const CrossCheckResultSchema = z.object({
  is_complete: z.boolean().default(false),
  missing_fields: z.array(z.string()).default([]),
  issues: z.array(z.string()).default([]),
  recommended_action: z.enum(["approved", "reread", "needs_review"]).default("approved"),
});
export type CrossCheckResult = z.infer<typeof CrossCheckResultSchema>;

export interface ExtractedRow {
  id?: number;
  source_file: string;
  image_hash: string;
  model_name: string;
  supplier: string;
  invoice_number: string;
  invoice_date: string;
  product_name: string;
  product_code: string;
  quantity: number;
  unit: string;
  unit_price: number | null;
  total_price: number | null;
  currency: string;
  notes: string;
  confidence: number;
  needs_review: boolean;
  review_notes: string;
  extraction_attempts: number;
  cross_check_model: string;
  extracted_at: string;
}
