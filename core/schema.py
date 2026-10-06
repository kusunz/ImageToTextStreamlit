"""Typed schemas for structured product extraction from images and cross-check review."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CurrencyCode = Literal["VND", "USD", "EUR", "JPY", "KRW", "CNY", "THB", "UNKNOWN"]
ReviewAction = Literal["approved", "reread", "needs_review"]


class ProductItem(BaseModel):
    """A single product line extracted from an image."""

    product_name: str = Field(default="", description="Product name")
    product_code: str = Field(default="", description="Product code or SKU if present")
    quantity: float = Field(default=0.0, description="Quantity")
    unit: str = Field(default="", description="Unit of measure, e.g. pcs, box, kg")
    unit_price: float | None = Field(default=None, description="Price per unit")
    total_price: float | None = Field(default=None, description="Total amount for this line")
    currency: CurrencyCode = Field(default="UNKNOWN", description="Currency code")
    notes: str = Field(default="", description="Additional line notes")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0"
    )

    @field_validator("product_name", "product_code", "unit", "notes", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("quantity", mode="before")
    @classmethod
    def _clean_quantity(cls, value: object) -> float:
        if value is None or value == "":
            return 0.0
        return float(value)


class ImageExtraction(BaseModel):
    """Structured result for one image."""

    supplier: str = Field(default="", description="Supplier or vendor name if identified")
    invoice_number: str = Field(default="", description="Invoice or receipt number")
    invoice_date: str = Field(default="", description="Invoice date string")
    staff_name: str = Field(default="", description="Staff or cashier name if present")
    total_amount: float | None = Field(default=None, description="Grand total on invoice if present")
    currency: CurrencyCode = Field(default="UNKNOWN", description="Document currency code")
    items: list[ProductItem] = Field(
        default_factory=list, description="List of products found in the image"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall confidence 0.0 to 1.0"
    )

    @field_validator("supplier", "invoice_number", "invoice_date", "staff_name", mode="before")
    @classmethod
    def _clean_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class CrossCheckResult(BaseModel):
    """Result of cross-checking product completeness via text-to-text review."""

    is_complete: bool = Field(
        default=False, description="True if all critical product fields are present and valid"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="List of missing required fields"
    )
    issues: list[str] = Field(
        default_factory=list, description="List of detected anomalies or quality issues"
    )
    recommended_action: ReviewAction = Field(
        default="approved", description="Recommended next action"
    )


class ExtractedRow(BaseModel):
    """Flat row stored in the database and shown in the review table."""

    source_file: str
    image_hash: str
    model_name: str
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    product_name: str = ""
    product_code: str = ""
    quantity: float = 0.0
    unit: str = ""
    unit_price: float | None = None
    total_price: float | None = None
    currency: str = "UNKNOWN"
    notes: str = ""
    confidence: float = 0.0
    needs_review: bool = False
    review_notes: str = ""
    extraction_attempts: int = 1
    cross_check_model: str = ""
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
