"""Offline tests for schema parsing, cross-check review, re-read flow, and fast query behavior."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from core import db, gemini_client
from core.config import Settings
from core.schema import ExtractedRow, ImageExtraction, ProductItem


def test_extraction_parses_json_and_cleans_text() -> None:
    payload = """
    {
      "supplier": "  Cong ty ABC  ",
      "invoice_number": "HD-001",
      "invoice_date": "2026-01-02",
      "staff_name": "Thu Ngan 01",
      "total_amount": 300000,
      "currency": "VND",
      "confidence": 0.95,
      "items": [
        {"product_name": "  Sua tuoi  ", "product_code": "SP01", "quantity": "12",
         "unit": "hop", "unit_price": 25000, "total_price": 300000, "confidence": 0.85}
      ]
    }
    """
    extraction = ImageExtraction.model_validate_json(payload)
    assert extraction.supplier == "Cong ty ABC"
    assert extraction.staff_name == "Thu Ngan 01"
    assert extraction.total_amount == 300000.0
    assert extraction.items[0].product_name == "Sua tuoi"
    assert extraction.items[0].quantity == 12.0


def test_model_names_match_user_specification() -> None:
    assert gemini_client.PRIMARY_MODEL_NAME == "gemini-3.5-flash-lite"
    assert gemini_client.PRIMARY_MODEL_LABEL == "Gemini 3.5 Flash Lite"
    assert gemini_client.REVIEW_MODEL_NAME == "gemma-4-26b"
    assert gemini_client.REVIEW_MODEL_LABEL == "Gemma 4 26B"


def test_cross_check_approves_complete_extraction() -> None:
    extraction = ImageExtraction(
        supplier="ABC Corp",
        invoice_number="INV-001",
        items=[
            ProductItem(
                product_name="Mineral Water 500ml",
                product_code="WAT500",
                quantity=10.0,
                unit="bottle",
                unit_price=5000.0,
                total_price=50000.0,
                currency="VND",
            )
        ],
    )
    result = gemini_client.local_cross_check(extraction)
    assert result.is_complete is True
    assert result.recommended_action == "approved"
    assert len(result.missing_fields) == 0


def test_cross_check_flags_incomplete_product_data() -> None:
    # Missing unit, empty product name, zero quantity
    extraction = ImageExtraction(
        items=[
            ProductItem(
                product_name="",
                quantity=0.0,
                unit="",
            )
        ]
    )
    result = gemini_client.local_cross_check(extraction)
    assert result.is_complete is False
    assert result.recommended_action == "reread"
    assert any("product_name" in f for f in result.missing_fields)
    assert any("quantity" in f for f in result.missing_fields)


def _row(
    name: str,
    code: str,
    quantity: float,
    content_hash: str = "hash-1",
    needs_review: bool = False,
    notes: str = "",
) -> ExtractedRow:
    return ExtractedRow(
        source_file="a.png",
        image_hash=content_hash,
        model_name="gemini-3.5-flash-lite",
        supplier="ABC",
        product_name=name,
        product_code=code,
        quantity=quantity,
        currency="VND",
        needs_review=needs_review,
        review_notes=notes,
        extraction_attempts=2 if needs_review else 1,
        cross_check_model="gemma-4-26b",
        extracted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_upsert_inserts_then_updates(tmp_path) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}"
    db.init_db(url)

    inserted, updated = db.upsert_rows(url, [_row("Sua", "SP01", 5)])
    assert (inserted, updated) == (1, 0)
    assert db.count_rows(url) == 1

    inserted, updated = db.upsert_rows(url, [_row("Sua", "SP01", 9, needs_review=True, notes="Unit missing")])
    assert (inserted, updated) == (0, 1)
    assert db.count_rows(url) == 1

    rows = db.fetch_rows(url)
    assert rows[0].quantity == 9.0
    assert rows[0].needs_review is True
    assert rows[0].review_notes == "Unit missing"


def test_fetch_filters_by_search_and_needs_review(tmp_path) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'search.db').as_posix()}"
    db.init_db(url)
    db.upsert_rows(
        url,
        [
            _row("Sua tuoi", "SP01", 5, "hash-1", needs_review=False),
            _row("Banh mi", "SP02", 3, "hash-2", needs_review=True, notes="Check quantity"),
        ],
    )

    t0 = time.perf_counter()
    needs_review_rows = db.fetch_rows(url, needs_review=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert len(needs_review_rows) == 1
    assert needs_review_rows[0].product_code == "SP02"
    assert db.count_rows(url, needs_review=True) == 1
    assert db.count_rows(url, needs_review=False) == 1
    assert elapsed_ms < 100.0


def test_settings_resolves_backends(tmp_path) -> None:
    sqlite_url = f"sqlite+pysqlite:///{(tmp_path / 'app.db').as_posix()}"
    postgres_url = "postgresql+psycopg://user:pass@localhost:5432/test"
    settings = Settings(
        gemini_api_key="test-key",
        database_url=postgres_url,
        sqlite_url=sqlite_url,
        postgres_url=postgres_url,
        model_page_size=100,
        sqlite_path=tmp_path / "app.db",
    )
    assert settings.resolve_url("SQLite") == sqlite_url
    assert settings.resolve_url("PostgreSQL") == postgres_url
