"""Service that turns uploaded images into persisted product rows with cross-check review."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from google import genai

from core import gemini_client
from core.schema import ExtractedRow, ImageExtraction


@dataclass
class ImageInput:
    """One image ready for extraction."""

    filename: str
    data: bytes
    mime_type: str


@dataclass
class ExtractionOutcome:
    """Aggregated result for a batch of images."""

    rows: list[ExtractedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_extractions: list[dict[str, object]] = field(default_factory=list)
    processed_files: int = 0
    needs_review_count: int = 0
    reread_count: int = 0


def image_hash(data: bytes) -> str:
    """Return a stable content hash for deduplication."""
    return hashlib.sha256(data).hexdigest()


def _rows_from_extraction(
    filename: str,
    content_hash: str,
    model_name: str,
    extraction: ImageExtraction,
    needs_review: bool,
    review_notes: str,
    attempts: int,
    cross_check_model: str,
) -> list[ExtractedRow]:
    now = datetime.now(UTC)
    rows: list[ExtractedRow] = []
    if not extraction.items:
        return rows
    for item in extraction.items:
        currency = item.currency if item.currency != "UNKNOWN" else extraction.currency
        rows.append(
            ExtractedRow(
                source_file=filename,
                image_hash=content_hash,
                model_name=model_name,
                supplier=extraction.supplier,
                invoice_number=extraction.invoice_number,
                invoice_date=extraction.invoice_date,
                product_name=item.product_name,
                product_code=item.product_code,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                total_price=item.total_price,
                currency=currency,
                notes=item.notes,
                confidence=item.confidence or extraction.confidence,
                needs_review=needs_review,
                review_notes=review_notes,
                extraction_attempts=attempts,
                cross_check_model=cross_check_model,
                extracted_at=now,
            )
        )
    return rows


def extract_batch(
    client: genai.Client,
    model_name: str,
    images: list[ImageInput],
    review_model: str = gemini_client.REVIEW_MODEL_NAME,
    temperature: float = 0.0,
) -> ExtractionOutcome:
    """Extract product rows with cross-check verification and re-read on missing fields."""
    outcome = ExtractionOutcome()
    for image in images:
        content_hash = image_hash(image.data)
        attempts = 1
        needs_review = False
        review_notes = ""

        # Step 1: Primary extraction with Gemini 3.5 Flash Lite
        try:
            extraction = gemini_client.extract_products(
                client=client,
                model_name=model_name,
                image_bytes=image.data,
                mime_type=image.mime_type,
                temperature=temperature,
            )
        except gemini_client.GeminiError as exc:
            outcome.errors.append(f"{image.filename}: {exc}")
            continue

        # Step 2: Cross-check review with Gemma 4 26B
        review = gemini_client.cross_check_with_gemma(
            client=client,
            review_model=review_model,
            extraction=extraction,
        )

        # Step 3: If incomplete, attempt re-read ("doc lai")
        if not review.is_complete:
            outcome.reread_count += 1
            attempts = 2
            try:
                second_extraction = gemini_client.extract_products(
                    client=client,
                    model_name=model_name,
                    image_bytes=image.data,
                    mime_type=image.mime_type,
                    temperature=temperature,
                    reread_issues=review.issues or review.missing_fields,
                )
                second_review = gemini_client.cross_check_with_gemma(
                    client=client,
                    review_model=review_model,
                    extraction=second_extraction,
                )
                extraction = second_extraction
                review = second_review
            except gemini_client.GeminiError as exc:
                outcome.errors.append(f"{image.filename} (reread warning): {exc}")

            # Step 4: If STILL incomplete after second pass, force "needs_review"
            if not review.is_complete:
                needs_review = True
                review_notes = "; ".join(review.issues or review.missing_fields or ["Incomplete product information"])
                outcome.needs_review_count += 1

        raw_dict = extraction.model_dump()
        raw_dict["source_file"] = image.filename
        raw_dict["image_hash"] = content_hash
        raw_dict["model_name"] = model_name
        raw_dict["needs_review"] = needs_review
        raw_dict["review_notes"] = review_notes
        raw_dict["extraction_attempts"] = attempts
        raw_dict["cross_check_model"] = review_model
        outcome.raw_extractions.append(raw_dict)

        rows = _rows_from_extraction(
            filename=image.filename,
            content_hash=content_hash,
            model_name=model_name,
            extraction=extraction,
            needs_review=needs_review,
            review_notes=review_notes,
            attempts=attempts,
            cross_check_model=review_model,
        )
        if not rows:
            outcome.errors.append(f"{image.filename}: no product lines detected")
        outcome.rows.extend(rows)
        outcome.processed_files += 1
    return outcome
