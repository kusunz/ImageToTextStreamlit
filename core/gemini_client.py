"""Google Gemini and Gemma client helpers: dynamic model listing, vision extraction, and text cross-check."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from google import genai
from google.genai import types

from core.schema import CrossCheckResult, ImageExtraction

# Primary model and text review model requested by user
PRIMARY_MODEL_NAME = "gemini-3.5-flash-lite"
PRIMARY_MODEL_LABEL = "Gemini 3.5 Flash Lite"

REVIEW_MODEL_NAME = "gemma-4-26b"
REVIEW_MODEL_LABEL = "Gemma 4 26B"

# Gemini requires lowercase mime types and only supports these image formats.
SUPPORTED_IMAGE_MIME = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
}

STRICT_EXTRACTION_SYSTEM_PROMPT = (
    "You are a rigorous, high-precision OCR and structured data extraction engine specialized in "
    "commercial product labels, retail receipts, packing slips, and invoices. You strictly extract "
    "factual data visible in the image into structured JSON matching the provided schema. "
    "Never fabricate, guess, or extrapolate missing values. Ensure complete and accurate extraction."
)

STRICT_EXTRACTION_PROMPT = (
    "Analyze the attached image and extract all distinct product line items. "
    "For every line item, strictly extract:\n"
    "1. 'product_name': The full descriptive name of the item (do not omit).\n"
    "2. 'product_code': The SKU, barcode, article number, or reference code if visible.\n"
    "3. 'quantity': The numerical quantity purchased or listed (must be a positive number).\n"
    "4. 'unit': The unit of measure (e.g., pcs, box, kg, pack, can, bottle).\n"
    "5. 'unit_price': The price per single unit (numeric, without currency symbols).\n"
    "6. 'total_price': The line total amount (numeric, without currency symbols).\n"
    "7. 'currency': The ISO currency code (e.g., VND, USD, EUR, etc., or UNKNOWN).\n"
    "8. 'notes': Any specific attributes like size, color, or batch number.\n"
    "9. 'confidence': Your confidence score between 0.0 and 1.0.\n\n"
    "Also extract document-level metadata:\n"
    "- 'supplier': Business name or seller.\n"
    "- 'invoice_number': Receipt, bill, or invoice identifier.\n"
    "- 'invoice_date': Document date string.\n"
    "- 'staff_name': Cashier, operator, or sales representative if present.\n"
    "- 'total_amount': Grand total amount on document if present.\n\n"
    "Ensure maximum completeness. Return valid JSON only."
)

STRICT_REREAD_PROMPT_TEMPLATE = (
    "CRITICAL SECOND-PASS INSPECTION: The initial extraction was flagged as INCOMPLETE or missing "
    "essential product information. Identified deficiencies: {issues_summary}.\n\n"
    "Please perform an exhaustive second examination of the image:\n"
    "1. Scrutinize all text lines, tables, headers, and itemized rows.\n"
    "2. Locate the full product name, item code/SKU, quantity, unit, and pricing for each item.\n"
    "3. Verify that every line has a positive quantity and a clear item name.\n"
    "Return the complete and corrected structured JSON."
)

STRICT_REVIEW_SYSTEM_PROMPT = (
    "You are an automated quality assurance auditor for commercial product extraction. "
    "Your role is to cross-check extracted product data for completeness, validity, and consistency."
)

STRICT_REVIEW_PROMPT_TEMPLATE = (
    "Review the following extracted invoice/product data for completeness and quality:\n\n"
    "{extracted_json}\n\n"
    "Audit criteria:\n"
    "1. Completeness: Every line item MUST have a non-empty, descriptive product name, a positive quantity (> 0), and a unit.\n"
    "2. Identification: Product code / SKU should be extracted if visible.\n"
    "3. Math consistency: If unit_price and total_price are both present, check if quantity * unit_price is approximately total_price.\n"
    "4. Document completeness: Check if supplier and invoice_number are identified.\n\n"
    "Return strict JSON matching the schema with fields:\n"
    "- 'is_complete': boolean (true if all items have complete product name, quantity > 0, and no critical omissions; false otherwise)\n"
    "- 'missing_fields': list of strings identifying missing fields\n"
    "- 'issues': list of strings describing any errors or incomplete details\n"
    "- 'recommended_action': string ('approved' if complete, 'reread' if critical fields are missing, 'needs_review' if persistent issues)"
)


class GeminiError(RuntimeError):
    """Raised for any recoverable Gemini interaction error."""


@dataclass(frozen=True)
class ModelInfo:
    """A trimmed view of an available Gemini model."""

    name: str
    display_name: str
    supports_image: bool


def _sanitize(message: str) -> str:
    """Remove potential API keys or long tokens from an error message."""
    cleaned = re.sub(r"AIza[0-9A-Za-z\-_]{10,}", "***", message)
    cleaned = re.sub(r"(?i)(key|token|secret)=([^&\s]+)", r"\1=***", cleaned)
    return cleaned.strip()


def build_client(api_key: str) -> genai.Client:
    """Create a Gemini client. Raises GeminiError when the key is missing."""
    if not api_key:
        raise GeminiError(
            "Missing Gemini API key. Set GEMINI_API_KEY in .env or Streamlit secrets."
        )
    try:
        return genai.Client(api_key=api_key)
    except Exception as exc:  # pragma: no cover - defensive
        raise GeminiError(f"Could not create Gemini client: {_sanitize(str(exc))}") from exc


def _model_supports_image(model: types.Model) -> bool:
    actions = model.supported_actions or []
    if "generateContent" not in actions:
        return False
    label = (model.name or "").lower()
    if "embedding" in label or "embed" in label:
        return False
    if "aqa" in label:
        return False
    return True


def list_vision_models(client: genai.Client, page_size: int = 200) -> list[ModelInfo]:
    """List models that can accept image input for generateContent."""
    try:
        config = types.ListModelsConfig(page_size=page_size)
        pager = client.models.list(config=config)
        models: Iterable[types.Model] = pager
        found: list[ModelInfo] = []
        seen: set[str] = set()
        for model in models:
            if not _model_supports_image(model):
                continue
            raw_name = model.name or ""
            short_name = raw_name.split("/")[-1] if raw_name else ""
            if not short_name or short_name in seen:
                continue
            seen.add(short_name)
            found.append(
                ModelInfo(
                    name=short_name,
                    display_name=model.display_name or short_name,
                    supports_image=True,
                )
            )

        # Ensure user's primary model is always present in options
        if PRIMARY_MODEL_NAME not in seen:
            found.append(
                ModelInfo(
                    name=PRIMARY_MODEL_NAME,
                    display_name=PRIMARY_MODEL_LABEL,
                    supports_image=True,
                )
            )

        return sorted(found, key=_model_sort_key)
    except Exception as exc:
        raise GeminiError(f"Could not list models: {_sanitize(str(exc))}") from exc


def _model_sort_key(info: ModelInfo) -> tuple[int, str]:
    """Prefer the requested primary model first, then flash models."""
    name = info.name.lower()
    if name == PRIMARY_MODEL_NAME:
        return (0, name)
    if "flash-lite" in name:
        return (1, name)
    if "flash" in name:
        return (2, name)
    if "pro" in name:
        return (3, name)
    return (4, name)


def guess_mime_type(filename: str, declared: str | None = None) -> str:
    """Resolve a supported image mime type from a filename or declared value."""
    if declared:
        normalized = declared.lower().strip()
        if normalized in SUPPORTED_IMAGE_MIME:
            return normalized
        if normalized in {"image/jpg", "image/pjpeg"}:
            return "image/jpeg"
    lowered = filename.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith((".heic", ".heif")):
        return "image/heic"
    raise GeminiError(f"Unsupported image type for file: {filename}")


def extract_products(
    client: genai.Client,
    model_name: str,
    image_bytes: bytes,
    mime_type: str,
    temperature: float = 0.0,
    reread_issues: list[str] | None = None,
) -> ImageExtraction:
    """Run vision extraction on one image and return a validated model."""
    if mime_type not in SUPPORTED_IMAGE_MIME:
        raise GeminiError(f"Unsupported image mime type: {mime_type}")
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    if reread_issues:
        issues_summary = "; ".join(reread_issues)
        prompt_text = STRICT_REREAD_PROMPT_TEMPLATE.format(issues_summary=issues_summary)
    else:
        prompt_text = STRICT_EXTRACTION_PROMPT

    config = types.GenerateContentConfig(
        system_instruction=STRICT_EXTRACTION_SYSTEM_PROMPT,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=ImageExtraction,
    )
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt_text, part],
            config=config,
        )
    except Exception as exc:
        raise GeminiError(f"Extraction failed for {model_name}: {_sanitize(str(exc))}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ImageExtraction):
        return parsed
    text = getattr(response, "text", None)
    if not text:
        raise GeminiError("Model returned no content for this image.")
    try:
        return ImageExtraction.model_validate_json(text)
    except Exception as exc:
        raise GeminiError(f"Model returned invalid JSON: {_sanitize(str(exc))}") from exc


def local_cross_check(extraction: ImageExtraction) -> CrossCheckResult:
    """Deterministic local cross-check for completeness."""
    missing: list[str] = []
    issues: list[str] = []

    if not extraction.items:
        return CrossCheckResult(
            is_complete=False,
            missing_fields=["items"],
            issues=["No product line items found in the extraction."],
            recommended_action="reread",
        )

    for idx, item in enumerate(extraction.items, start=1):
        line_prefix = f"Line {idx}"
        if not item.product_name or len(item.product_name.strip()) < 2:
            missing.append(f"{line_prefix}: product_name")
            issues.append(f"{line_prefix} is missing a descriptive product name.")
        if item.quantity <= 0.0:
            missing.append(f"{line_prefix}: quantity")
            issues.append(f"{line_prefix} quantity must be greater than zero (got {item.quantity}).")
        if not item.unit:
            missing.append(f"{line_prefix}: unit")
            issues.append(f"{line_prefix} ({item.product_name or 'item'}) is missing a unit of measure.")

        if item.unit_price is not None and item.total_price is not None and item.quantity > 0:
            expected = item.quantity * item.unit_price
            diff = abs(expected - item.total_price)
            if diff > max(1.0, 0.05 * item.total_price):
                issues.append(
                    f"{line_prefix} math mismatch: {item.quantity} * {item.unit_price} != {item.total_price}"
                )

    if not extraction.supplier and not extraction.invoice_number:
        issues.append("Neither supplier nor invoice number was identified.")

    is_complete = len(missing) == 0
    recommended_action = "approved" if is_complete else "reread"
    return CrossCheckResult(
        is_complete=is_complete,
        missing_fields=missing,
        issues=issues,
        recommended_action=recommended_action,
    )


def cross_check_with_gemma(
    client: genai.Client,
    review_model: str,
    extraction: ImageExtraction,
) -> CrossCheckResult:
    """Run text-to-text review using Gemma 4 26B (or fallback to local cross-check)."""
    extracted_json = extraction.model_dump_json(indent=2)
    prompt = STRICT_REVIEW_PROMPT_TEMPLATE.format(extracted_json=extracted_json)

    config = types.GenerateContentConfig(
        system_instruction=STRICT_REVIEW_SYSTEM_PROMPT,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=CrossCheckResult,
    )

    try:
        response = client.models.generate_content(
            model=review_model,
            contents=[prompt],
            config=config,
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, CrossCheckResult):
            return parsed
        text = getattr(response, "text", None)
        if text:
            return CrossCheckResult.model_validate_json(text)
    except Exception:
        # Resilient fallback to local deterministic rule-based check
        pass

    return local_cross_check(extraction)
