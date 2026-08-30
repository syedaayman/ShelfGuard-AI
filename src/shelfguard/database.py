import csv
import hashlib
import os
import uuid
import zoneinfo
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from shelfguard.config import settings

BUSINESS_TIMEZONE = zoneinfo.ZoneInfo("Asia/Kolkata")

engine = create_engine(settings.db_path, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id: Any = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sku: Any = Column(String, unique=True, nullable=False, index=True)
    product_name: Any = Column(String, nullable=False)
    category: Any = Column(String, nullable=False)
    manufacturer: Any = Column(String, nullable=True)
    base_price: Any = Column(Float, nullable=False)
    mrp: Any = Column(Float, nullable=True)
    created_at: Any = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    batches = relationship("InventoryBatch", back_populates="product", cascade="all, delete-orphan")


class InventoryBatch(Base):
    __tablename__ = "inventory_batches"

    id: Any = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id: Any = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_number: Any = Column(String, nullable=True, index=True)
    internal_batch_id: Any = Column(String, unique=True, nullable=False, index=True)
    manufacturing_date: Any = Column(String, nullable=True)
    expiry_date: Any = Column(String, nullable=False)
    stock_quantity: Any = Column(Integer, nullable=False, default=0)
    current_discount: Any = Column(Float, default=0.0)
    daily_demand: Any = Column(Integer, nullable=False, default=0)
    status: Any = Column(String, default="ACTIVE")
    created_at: Any = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    product = relationship("Product", back_populates="batches")


class TaxAuditLedger(Base):
    __tablename__ = "tax_audit_ledger"

    audit_id: Any = Column(Integer, primary_key=True, index=True, autoincrement=True)
    transaction_id: Any = Column(String, unique=True, nullable=False)
    total_sale_amount_cents: Any = Column(Integer, nullable=False)
    tax_collected_cents: Any = Column(Integer, nullable=False)
    timestamp: Any = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    previous_hash: Any = Column(String, nullable=False)
    record_hash: Any = Column(String, nullable=False)


class NgoDonation(Base):
    __tablename__ = "ngo_donations"

    donation_id: Any = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id: Any = Column(Integer, ForeignKey("inventory_batches.id"), nullable=False)
    batch_number: Any = Column(String, nullable=True)
    sku: Any = Column(String, nullable=False)
    ngo_name: Any = Column(String, nullable=False)
    product_name: Any = Column(String, nullable=False)
    quantity: Any = Column(Integer, nullable=False)
    estimated_value: Any = Column(Float, nullable=False)
    dispatch_timestamp: Any = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    requested_at: Any = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    approved_at: Any = Column(DateTime, nullable=True)
    status: Any = Column(String, default="PENDING")
    tax_receipt_status: Any = Column(String, default="VERIFIED_80G")
    tax_receipt_reference: Any = Column(String, unique=True, nullable=False)


def init_db() -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        # Check if mrp column exists in products table, add if missing
        try:
            conn.execute(text("ALTER TABLE products ADD COLUMN mrp FLOAT;"))
        except Exception:
            pass  # Column already exists

        # Add missing columns to ngo_donations if table existed prior to Phase 9
        for col_def in [
            ("requested_at", "DATETIME"),
            ("approved_at", "DATETIME"),
            ("status", "VARCHAR DEFAULT 'PENDING'"),
        ]:
            try:
                col_name, col_type = col_def
                conn.execute(text(f"ALTER TABLE ngo_donations ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_internal_batch_id(
    sku: str, expiry_date: str, batch_number: Optional[str] = None, unique_suffix: bool = False
) -> str:
    """
    Generate a deterministic internal batch ID based on SKU, batch_number / expiry_date.
    If unique_suffix is True, adds a random suffix to guarantee uniqueness for force_new_batch.
    """
    if batch_number:
        clean_batch = batch_number.strip().replace(" ", "-").upper()
        base_id = f"BATCH-{sku}-{clean_batch}"
    else:
        hash_input = f"{sku}-{expiry_date}".encode("utf-8")
        hash_val = hashlib.sha256(hash_input).hexdigest()[:8].upper()
        base_id = f"INT-{hash_val}-{expiry_date}"

    if unique_suffix:
        suffix = uuid.uuid4().hex[:6].upper()
        return f"{base_id}-{suffix}"

    return base_id


def find_existing_batch(
    db: Session,
    product_id: int,
    batch_number: Optional[str],
    expiry_date: str,
    manufacturing_date: Optional[str] = None,
) -> Optional[InventoryBatch]:
    """
    Find matching existing batch for a product:
    1. Product + exact batch_number (if batch_number is present and not empty)
    2. Product + manufacturing_date + expiry_date (if batch_number is absent)
    3. Product + expiry_date (fallback when manufacturing_date is also absent)
    """
    if batch_number and batch_number.strip():
        clean_batch = batch_number.strip()
        batch = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.product_id == product_id,
                InventoryBatch.batch_number.ilike(clean_batch),
            )
            .first()
        )
        if batch:
            return batch

    # Fallback matching without batch_number
    query = db.query(InventoryBatch).filter(
        InventoryBatch.product_id == product_id, InventoryBatch.expiry_date == expiry_date
    )
    if manufacturing_date:
        query = query.filter(InventoryBatch.manufacturing_date == manufacturing_date)

    return query.first()


def resolve_product(
    db: Session,
    sku: Optional[str],
    product_name: str,
    manufacturer: Optional[str] = None,
    base_price: Optional[float] = None,
    mrp: Optional[float] = None,
    category: Optional[str] = None,
) -> Product:
    """
    Resolve existing product or create a new one.
    Matches primarily on exact/normalized SKU, or normalized product_name.
    """
    product = None
    if sku and sku.strip():
        clean_sku = sku.strip().upper()
        product = db.query(Product).filter(Product.sku == clean_sku).first()

    if not product and product_name and product_name.strip():
        clean_name = product_name.strip()
        # Search by exact/case-insensitive product name
        query = db.query(Product).filter(Product.product_name.ilike(clean_name))
        if manufacturer and manufacturer.strip():
            query = query.filter(Product.manufacturer.ilike(manufacturer.strip()))
        product = query.first()

    if not product:
        # Generate clean SKU
        if sku and sku.strip():
            final_sku = sku.strip().upper()
        else:
            name_slug = "".join(c for c in product_name.upper() if c.isalnum())[:6]
            hash_tag = (
                hashlib.md5(
                    f"{product_name}-{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
                )
                .hexdigest()[:6]
                .upper()
            )
            final_sku = f"SKU-{name_slug}-{hash_tag}"

        clean_cat = category.strip() if category and category.strip() else "UNCATEGORIZED"
        product = Product(
            sku=final_sku,
            product_name=product_name.strip(),
            category=clean_cat,
            manufacturer=manufacturer.strip() if manufacturer else None,
            base_price=float(base_price if base_price is not None else (mrp or 0.0)),
            mrp=mrp if mrp is not None else None,
        )
        db.add(product)
        db.flush()
    else:
        # Update MRP, manufacturer, or category if available and currently missing
        if mrp is not None and getattr(product, "mrp", None) is None:
            setattr(product, "mrp", mrp)
        if manufacturer and not getattr(product, "manufacturer", None):
            setattr(product, "manufacturer", manufacturer.strip())
        if category and category.strip() and (not product.category or product.category == "UNCATEGORIZED"):
            setattr(product, "category", category.strip())

    return product


def calculate_expiry_status(expiry_date_str: str, ref_time: Optional[datetime] = None) -> dict:
    """
    Authoritative backend function for dynamic expiry status calculation.
    Timezone: Asia/Kolkata.
    Rule: Date-only expiries (YYYY-MM-DD) default to 23:59:59 Asia/Kolkata on that expiry date.
    Status evaluation order:
      1. EXPIRED: remaining_hours <= 0
      2. DONATION: 0 < remaining_hours <= 6
      3. CRITICAL: 6 < remaining_hours <= 48
      4. NEAR_EXPIRY: 48 < remaining_hours <= 168
      5. SAFE: remaining_hours > 168
    Returns dict with status, remaining_hours, remaining_days, remaining_text.
    """
    try:
        clean_str = expiry_date_str.strip()
        if "T" in clean_str:
            dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                expiry_dt = dt.replace(tzinfo=BUSINESS_TIMEZONE)
            else:
                expiry_dt = dt.astimezone(BUSINESS_TIMEZONE)
        elif " " in clean_str:
            naive_dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            expiry_dt = naive_dt.replace(tzinfo=BUSINESS_TIMEZONE)
        else:
            naive_dt = datetime.strptime(clean_str, "%Y-%m-%d")
            expiry_dt = naive_dt.replace(hour=23, minute=59, second=59, tzinfo=BUSINESS_TIMEZONE)

        if ref_time is not None:
            now = ref_time if ref_time.tzinfo else ref_time.replace(tzinfo=BUSINESS_TIMEZONE)
            now = now.astimezone(BUSINESS_TIMEZONE)
        else:
            now = datetime.now(BUSINESS_TIMEZONE)

        remaining_hours = (expiry_dt - now).total_seconds() / 3600.0

        if remaining_hours <= 0:
            status = "EXPIRED"
        elif remaining_hours <= 6.0:
            status = "DONATION"
        elif remaining_hours <= 48.0:
            status = "CRITICAL"
        elif remaining_hours <= 168.0:
            status = "NEAR_EXPIRY"
        else:
            status = "SAFE"

        rem_h_rounded = round(remaining_hours, 2)
        rem_d_rounded = round(remaining_hours / 24.0, 1)

        if remaining_hours <= 0:
            abs_h = abs(remaining_hours)
            if abs_h < 1.0:
                remaining_text = "Expired just now"
            elif abs_h < 24.0:
                hours_val = max(1, round(abs_h))
                remaining_text = f"Expired {hours_val} hour{'s' if hours_val > 1 else ''} ago"
            else:
                days_val = max(1, round(abs_h / 24.0))
                remaining_text = f"Expired {days_val} day{'s' if days_val > 1 else ''} ago"
        else:
            if remaining_hours <= 24.0:
                hours_val = max(1, round(remaining_hours))
                remaining_text = f"Expires in {hours_val} hour{'s' if hours_val > 1 else ''}"
            elif remaining_hours <= 48.0:
                remaining_text = "Expires tomorrow"
            else:
                days_val = round(remaining_hours / 24.0)
                remaining_text = f"Expires in {days_val} day{'s' if days_val > 1 else ''}"

        return {
            "status": status,
            "remaining_hours": rem_h_rounded,
            "remaining_days": rem_d_rounded,
            "remaining_text": remaining_text,
        }
    except Exception:
        return {
            "status": "SAFE",
            "remaining_hours": 9999.0,
            "remaining_days": 416.6,
            "remaining_text": "Valid",
        }


def compute_dynamic_status(
    expiry_date_str: str, current_status: str = "ACTIVE"
) -> tuple[str, float]:
    """
    Computes dynamic inventory lifecycle status and remaining hours.
    Maintains compatibility with legacy callers.
    """
    if current_status == "NGO_DISPATCH":
        return "NGO_DISPATCH", 0.0

    res = calculate_expiry_status(expiry_date_str)
    return res["status"], res["remaining_hours"]


def load_csv_to_db(db: Session, csv_path: str = "data/mock_inventory.csv") -> dict:
    """Loads live inventory data from CSV mapping product->Product and rows->InventoryBatch."""
    stats = {"read": 0, "products_inserted": 0, "batches_inserted": 0, "rejected": 0}

    if not os.path.exists(csv_path):
        if os.path.exists("data/perishable_goods_management.csv"):
            csv_path = "data/perishable_goods_management.csv"
        else:
            raise FileNotFoundError(f"CSV file not found at {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        products_map = {}
        batches_map = {}

        for row in reader:
            stats["read"] += 1
            try:
                sku = (row.get("sku") or row.get("product_id") or "").strip()
                p_name = (row.get("product_name") or "").strip()
                exp_date = (row.get("expiry_date") or row.get("expiration_date") or "").strip()

                if not sku or not p_name or not exp_date:
                    raise ValueError("Missing essential fields (sku, product_name, expiry_date)")

                category = (row.get("category") or "UNCATEGORIZED").strip()
                mfr = (row.get("manufacturer") or "").strip() or None
                base_price = float(row.get("base_price", 0.0))
                mrp_val = (
                    float(row.get("mrp"))
                    if row.get("mrp") and str(row.get("mrp")).strip()
                    else None
                )

                if sku not in products_map:
                    products_map[sku] = {
                        "sku": sku,
                        "product_name": p_name,
                        "category": category,
                        "manufacturer": mfr,
                        "base_price": base_price,
                        "mrp": mrp_val,
                    }

                batch_no = (row.get("batch_number") or "").strip() or None
                mfg_date = (row.get("manufacturing_date") or "").strip() or None
                stock_qty = int(row.get("stock_quantity") or row.get("initial_quantity") or 0)
                demand = int(row.get("daily_demand") or 0)
                raw_status = (row.get("status") or "ACTIVE").strip()

                internal_batch_id = generate_internal_batch_id(sku, exp_date, batch_number=batch_no)

                if internal_batch_id not in batches_map:
                    batches_map[internal_batch_id] = {
                        "sku": sku,
                        "batch_number": batch_no,
                        "internal_batch_id": internal_batch_id,
                        "manufacturing_date": mfg_date,
                        "expiry_date": exp_date,
                        "stock_quantity": stock_qty,
                        "daily_demand": demand,
                        "status": raw_status,
                    }
                else:
                    batches_map[internal_batch_id]["stock_quantity"] += stock_qty

            except (ValueError, KeyError, TypeError):
                stats["rejected"] += 1
                continue

        # Upsert Products
        if products_map:
            stmt = insert(Product).on_conflict_do_update(
                index_elements=["sku"],
                set_={
                    "product_name": insert(Product).excluded.product_name,
                    "category": insert(Product).excluded.category,
                    "manufacturer": insert(Product).excluded.manufacturer,
                    "base_price": insert(Product).excluded.base_price,
                    "mrp": insert(Product).excluded.mrp,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            db.execute(stmt, list(products_map.values()))
            db.commit()
            stats["products_inserted"] = len(products_map)

        product_rows = db.query(Product.id, Product.sku).all()
        sku_to_id = {row.sku: row.id for row in product_rows}

        batches_to_insert = []
        for b in batches_map.values():
            b_data = dict(b)
            del b_data["sku"]
            b_data["product_id"] = sku_to_id[b["sku"]]
            batches_to_insert.append(b_data)

        if batches_to_insert:
            stmt_batch = insert(InventoryBatch).on_conflict_do_update(
                index_elements=["internal_batch_id"],
                set_={
                    "batch_number": insert(InventoryBatch).excluded.batch_number,
                    "manufacturing_date": insert(InventoryBatch).excluded.manufacturing_date,
                    "expiry_date": insert(InventoryBatch).excluded.expiry_date,
                    "stock_quantity": insert(InventoryBatch).excluded.stock_quantity,
                    "daily_demand": insert(InventoryBatch).excluded.daily_demand,
                    "status": insert(InventoryBatch).excluded.status,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            db.execute(stmt_batch, batches_to_insert)
            db.commit()
            stats["batches_inserted"] = len(batches_to_insert)

    return stats
