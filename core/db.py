"""Database layer supporting SQLite (default) and Postgres via DATABASE_URL."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Sequence

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    delete as sa_delete,
    event,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from core.schema import ExtractedRow

_ENGINES: dict[str, Engine] = {}
_SESSION_FACTORIES: dict[str, sessionmaker[Session]] = {}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class ProductRecord(Base):
    """A single product line persisted in the database."""

    __tablename__ = "product_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(512), default="")
    image_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    model_name: Mapped[str] = mapped_column(String(128), default="")
    supplier: Mapped[str] = mapped_column(String(512), default="", index=True)
    invoice_number: Mapped[str] = mapped_column(String(255), default="")
    invoice_date: Mapped[str] = mapped_column(String(64), default="")
    product_name: Mapped[str] = mapped_column(String(512), default="", index=True)
    product_code: Mapped[str] = mapped_column(String(255), default="", index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(64), default="")
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    notes: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    extraction_attempts: Mapped[int] = mapped_column(Integer, default=1)
    cross_check_model: Mapped[str] = mapped_column(String(128), default="")
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_records_dedup", "image_hash", "product_code", "product_name"),
        Index("ix_records_supplier_invoice", "supplier", "invoice_number"),
        Index("ix_records_search_name_code", "product_name", "product_code"),
        Index("ix_records_needs_review", "needs_review"),
    )


def _build_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine = create_engine(
            database_url,
            future=True,
            connect_args=connect_args,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
            cursor = getattr(dbapi_connection, "cursor", None)
            if cursor:
                cur = cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()

        return engine

    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def get_engine(database_url: str) -> Engine:
    """Return a cached engine for the given URL."""
    engine = _ENGINES.get(database_url)
    if engine is None:
        engine = _build_engine(database_url)
        _ENGINES[database_url] = engine
    return engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    """Return a cached session factory for the given URL."""
    factory = _SESSION_FACTORIES.get(database_url)
    if factory is None:
        factory = sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
        _SESSION_FACTORIES[database_url] = factory
    return factory


def init_db(database_url: str) -> None:
    """Create tables, indexes, and apply column migrations if they do not exist yet."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)

    # Seamless column migration for existing tables
    is_sqlite = database_url.startswith("sqlite")
    with engine.begin() as conn:
        if is_sqlite:
            result = conn.execute(text("PRAGMA table_info(product_records)"))
            existing_cols = {row[1] for row in result.fetchall()}
            if "needs_review" not in existing_cols:
                conn.execute(text("ALTER TABLE product_records ADD COLUMN needs_review BOOLEAN DEFAULT 0"))
            if "review_notes" not in existing_cols:
                conn.execute(text("ALTER TABLE product_records ADD COLUMN review_notes TEXT DEFAULT ''"))
            if "extraction_attempts" not in existing_cols:
                conn.execute(text("ALTER TABLE product_records ADD COLUMN extraction_attempts INTEGER DEFAULT 1"))
            if "cross_check_model" not in existing_cols:
                conn.execute(text("ALTER TABLE product_records ADD COLUMN cross_check_model VARCHAR(128) DEFAULT ''"))
        else:
            conn.execute(text("ALTER TABLE product_records ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE product_records ADD COLUMN IF NOT EXISTS review_notes TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE product_records ADD COLUMN IF NOT EXISTS extraction_attempts INTEGER DEFAULT 1"))
            conn.execute(text("ALTER TABLE product_records ADD COLUMN IF NOT EXISTS cross_check_model VARCHAR(128) DEFAULT ''"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_records_needs_review ON product_records(needs_review)"))


def _dedup_key(row: ExtractedRow) -> tuple[str, str, str]:
    return (row.image_hash, row.product_code.strip().lower(), row.product_name.strip().lower())


def upsert_rows(database_url: str, rows: Sequence[ExtractedRow]) -> tuple[int, int]:
    """Insert or update rows. Returns (inserted, updated) counts."""
    if not rows:
        return (0, 0)
    factory = get_session_factory(database_url)
    inserted = 0
    updated = 0
    with factory() as session:
        existing: dict[tuple[str, str, str], ProductRecord] = {}
        for row in rows:
            key = _dedup_key(row)
            if key in existing:
                continue
            record = session.execute(
                select(ProductRecord).where(
                    ProductRecord.image_hash == row.image_hash,
                    func.lower(ProductRecord.product_code) == row.product_code.strip().lower(),
                    func.lower(ProductRecord.product_name) == row.product_name.strip().lower(),
                )
            ).scalars().first()
            if record is not None:
                existing[key] = record
        for row in rows:
            key = _dedup_key(row)
            record = existing.get(key)
            if record is None:
                record = ProductRecord(
                    source_file=row.source_file,
                    image_hash=row.image_hash,
                    model_name=row.model_name,
                    extracted_at=row.extracted_at,
                )
                session.add(record)
                existing[key] = record
                inserted += 1
            else:
                updated += 1
            record.supplier = row.supplier
            record.invoice_number = row.invoice_number
            record.invoice_date = row.invoice_date
            record.product_name = row.product_name
            record.product_code = row.product_code
            record.quantity = row.quantity
            record.unit = row.unit
            record.unit_price = row.unit_price
            record.total_price = row.total_price
            record.currency = row.currency
            record.notes = row.notes
            record.confidence = row.confidence
            record.needs_review = row.needs_review
            record.review_notes = row.review_notes
            record.extraction_attempts = row.extraction_attempts
            record.cross_check_model = row.cross_check_model
            record.updated_at = datetime.now(UTC)
        session.commit()
    return (inserted, updated)


def fetch_rows(
    database_url: str,
    search: str = "",
    supplier: str = "",
    needs_review: bool | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[ExtractedRow]:
    """Fetch stored rows with optional text and review status filters, newest first."""
    factory = get_session_factory(database_url)
    with factory() as session:
        stmt = select(ProductRecord)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                ProductRecord.product_name.ilike(like)
                | ProductRecord.product_code.ilike(like)
                | ProductRecord.notes.ilike(like)
            )
        if supplier:
            stmt = stmt.where(ProductRecord.supplier == supplier)
        if needs_review is not None:
            stmt = stmt.where(ProductRecord.needs_review == needs_review)
        stmt = stmt.order_by(ProductRecord.id.desc()).limit(limit).offset(offset)
        records: Iterable[ProductRecord] = session.execute(stmt).scalars().all()
        return [_to_row(record) for record in records]


def count_rows(database_url: str, needs_review: bool | None = None) -> int:
    """Return the total number of stored rows, optionally filtered by review state."""
    factory = get_session_factory(database_url)
    with factory() as session:
        stmt = select(func.count(ProductRecord.id))
        if needs_review is not None:
            stmt = stmt.where(ProductRecord.needs_review == needs_review)
        return int(session.execute(stmt).scalar_one())


def list_suppliers(database_url: str) -> list[str]:
    """Return distinct non-empty supplier names."""
    factory = get_session_factory(database_url)
    with factory() as session:
        stmt = (
            select(ProductRecord.supplier)
            .where(ProductRecord.supplier != "")
            .distinct()
            .order_by(ProductRecord.supplier)
        )
        return [value for value in session.execute(stmt).scalars().all() if value]


def delete_rows(database_url: str, row_ids: Sequence[int]) -> int:
    """Delete rows by id. Returns the number of deleted rows."""
    if not row_ids:
        return 0
    factory = get_session_factory(database_url)
    with factory() as session:
        result = session.execute(sa_delete(ProductRecord).where(ProductRecord.id.in_(row_ids)))
        session.commit()
        return int(result.rowcount or 0)


def _to_row(record: ProductRecord) -> ExtractedRow:
    return ExtractedRow(
        source_file=record.source_file,
        image_hash=record.image_hash,
        model_name=record.model_name,
        supplier=record.supplier,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        product_name=record.product_name,
        product_code=record.product_code,
        quantity=record.quantity,
        unit=record.unit,
        unit_price=record.unit_price,
        total_price=record.total_price,
        currency=record.currency,
        notes=record.notes,
        confidence=record.confidence,
        needs_review=record.needs_review,
        review_notes=record.review_notes,
        extraction_attempts=record.extraction_attempts,
        cross_check_model=record.cross_check_model,
        extracted_at=record.extracted_at,
    )
