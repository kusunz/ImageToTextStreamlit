import { Pool } from "pg";
import { ExtractedRow } from "../types/schema";

let pool: Pool | null = null;
const memoryStore: ExtractedRow[] = [];

function getPool(): Pool | null {
  const connectionString =
    process.env.POSTGRES_URL ||
    process.env.DATABASE_URL ||
    process.env.POSTGRES_PRISMA_URL;

  if (!connectionString) {
    return null;
  }

  if (!pool) {
    pool = new Pool({
      connectionString,
      ssl: connectionString.includes("localhost") ? false : { rejectUnauthorized: false },
      max: 10,
    });
  }
  return pool;
}

export async function initDb(): Promise<void> {
  const p = getPool();
  if (!p) return;

  await p.query(`
    CREATE TABLE IF NOT EXISTS product_records (
      id SERIAL PRIMARY KEY,
      source_file VARCHAR(512) DEFAULT '',
      image_hash VARCHAR(64) DEFAULT '',
      model_name VARCHAR(128) DEFAULT '',
      supplier VARCHAR(512) DEFAULT '',
      invoice_number VARCHAR(255) DEFAULT '',
      invoice_date VARCHAR(64) DEFAULT '',
      product_name VARCHAR(512) DEFAULT '',
      product_code VARCHAR(255) DEFAULT '',
      quantity DOUBLE PRECISION DEFAULT 0.0,
      unit VARCHAR(64) DEFAULT '',
      unit_price DOUBLE PRECISION,
      total_price DOUBLE PRECISION,
      currency VARCHAR(16) DEFAULT 'UNKNOWN',
      notes TEXT DEFAULT '',
      confidence DOUBLE PRECISION DEFAULT 0.0,
      needs_review BOOLEAN DEFAULT FALSE,
      review_notes TEXT DEFAULT '',
      extraction_attempts INTEGER DEFAULT 1,
      cross_check_model VARCHAR(128) DEFAULT '',
      extracted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_records_dedup ON product_records(image_hash, product_code, product_name);
    CREATE INDEX IF NOT EXISTS ix_records_supplier_invoice ON product_records(supplier, invoice_number);
    CREATE INDEX IF NOT EXISTS ix_records_search ON product_records(product_name, product_code);
    CREATE INDEX IF NOT EXISTS ix_records_needs_review ON product_records(needs_review);
  `);
}

export async function upsertRows(rows: ExtractedRow[]): Promise<{ inserted: number; updated: number }> {
  if (rows.length === 0) return { inserted: 0, updated: 0 };
  const p = getPool();

  if (!p) {
    // Memory store fallback for zero-config
    let inserted = 0;
    let updated = 0;
    for (const r of rows) {
      const idx = memoryStore.findIndex(
        (m) =>
          m.image_hash === r.image_hash &&
          m.product_code.toLowerCase() === r.product_code.toLowerCase() &&
          m.product_name.toLowerCase() === r.product_name.toLowerCase()
      );
      if (idx >= 0) {
        memoryStore[idx] = { ...memoryStore[idx], ...r };
        updated++;
      } else {
        memoryStore.push({ ...r, id: memoryStore.length + 1 });
        inserted++;
      }
    }
    return { inserted, updated };
  }

  await initDb();
  let inserted = 0;
  let updated = 0;

  for (const r of rows) {
    const existing = await p.query(
      `SELECT id FROM product_records
       WHERE image_hash = $1 AND LOWER(product_code) = LOWER($2) AND LOWER(product_name) = LOWER($3)
       LIMIT 1`,
      [r.image_hash, r.product_code, r.product_name]
    );

    if (existing.rows.length > 0) {
      await p.query(
        `UPDATE product_records SET
          supplier = $1, invoice_number = $2, invoice_date = $3,
          quantity = $4, unit = $5, unit_price = $6, total_price = $7,
          currency = $8, notes = $9, confidence = $10, needs_review = $11,
          review_notes = $12, extraction_attempts = $13, cross_check_model = $14,
          updated_at = CURRENT_TIMESTAMP
         WHERE id = $15`,
        [
          r.supplier, r.invoice_number, r.invoice_date,
          r.quantity, r.unit, r.unit_price, r.total_price,
          r.currency, r.notes, r.confidence, r.needs_review,
          r.review_notes, r.extraction_attempts, r.cross_check_model,
          existing.rows[0].id,
        ]
      );
      updated++;
    } else {
      await p.query(
        `INSERT INTO product_records (
          source_file, image_hash, model_name, supplier, invoice_number, invoice_date,
          product_name, product_code, quantity, unit, unit_price, total_price,
          currency, notes, confidence, needs_review, review_notes, extraction_attempts,
          cross_check_model, extracted_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)`,
        [
          r.source_file, r.image_hash, r.model_name, r.supplier, r.invoice_number, r.invoice_date,
          r.product_name, r.product_code, r.quantity, r.unit, r.unit_price, r.total_price,
          r.currency, r.notes, r.confidence, r.needs_review, r.review_notes, r.extraction_attempts,
          r.cross_check_model, r.extracted_at,
        ]
      );
      inserted++;
    }
  }

  return { inserted, updated };
}

export async function fetchRows(params: {
  search?: string;
  supplier?: string;
  needs_review?: boolean | null;
  limit?: number;
  offset?: number;
}): Promise<{ rows: ExtractedRow[]; total: number }> {
  const p = getPool();
  const limit = params.limit || 100;
  const offset = params.offset || 0;

  if (!p) {
    let filtered = [...memoryStore];
    if (params.search) {
      const q = params.search.toLowerCase();
      filtered = filtered.filter(
        (r) =>
          r.product_name.toLowerCase().includes(q) ||
          r.product_code.toLowerCase().includes(q) ||
          r.notes.toLowerCase().includes(q)
      );
    }
    if (params.supplier) {
      filtered = filtered.filter((r) => r.supplier === params.supplier);
    }
    if (params.needs_review !== undefined && params.needs_review !== null) {
      filtered = filtered.filter((r) => r.needs_review === params.needs_review);
    }
    return {
      rows: filtered.slice(offset, offset + limit),
      total: filtered.length,
    };
  }

  await initDb();
  const conditions: string[] = [];
  const values: (string | boolean | number)[] = [];

  if (params.search) {
    values.push(`%${params.search}%`);
    conditions.push(`(product_name ILIKE $${values.length} OR product_code ILIKE $${values.length} OR notes ILIKE $${values.length})`);
  }
  if (params.supplier) {
    values.push(params.supplier);
    conditions.push(`supplier = $${values.length}`);
  }
  if (params.needs_review !== undefined && params.needs_review !== null) {
    values.push(params.needs_review);
    conditions.push(`needs_review = $${values.length}`);
  }

  const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const countRes = await p.query(`SELECT COUNT(*) as count FROM product_records ${whereClause}`, values);
  const total = parseInt(countRes.rows[0].count, 10);

  values.push(limit, offset);
  const query = `
    SELECT * FROM product_records
    ${whereClause}
    ORDER BY id DESC
    LIMIT $${values.length - 1} OFFSET $${values.length}
  `;
  const res = await p.query(query, values);
  return { rows: res.rows, total };
}
