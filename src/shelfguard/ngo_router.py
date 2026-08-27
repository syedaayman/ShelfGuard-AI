import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from shelfguard.database import (
    BUSINESS_TIMEZONE,
    InventoryBatch,
    NgoDonation,
    Product,
    calculate_expiry_status,
)
from shelfguard.schemas import DonationCandidate

logger = logging.getLogger(__name__)


def process_pending_donations(db: Session) -> List[NgoDonation]:
    """
    Checks and transitions PENDING donation requests that have reached 120 seconds.
    Deducts inventory stock transactionally and idempotently.
    """
    now = datetime.now(BUSINESS_TIMEZONE)
    pending_donations = db.query(NgoDonation).filter(NgoDonation.status == "PENDING").all()

    processed = []
    for donation in pending_donations:
        req_at = donation.requested_at or donation.dispatch_timestamp
        if req_at:
            if req_at.tzinfo is None:
                req_at = req_at.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TIMEZONE)
            else:
                req_at = req_at.astimezone(BUSINESS_TIMEZONE)
        else:
            req_at = now

        elapsed = (now - req_at).total_seconds()
        if elapsed >= 120.0:
            try:
                batch = (
                    db.query(InventoryBatch)
                    .filter(InventoryBatch.id == donation.batch_id)
                    .with_for_update()
                    .first()
                )

                if batch and batch.stock_quantity >= donation.quantity:
                    batch.stock_quantity -= donation.quantity
                    batch.updated_at = datetime.now(timezone.utc)
                    donation.status = "APPROVED"
                    donation.approved_at = datetime.now(timezone.utc)
                else:
                    avail_qty = batch.stock_quantity if batch else 0
                    logger.warning(
                        f"Insufficient stock to approve donation {donation.donation_id}. "
                        f"Requested: {donation.quantity}, Available: {avail_qty}"
                    )
                    donation.status = "CANCELLED"
                    donation.approved_at = None

                db.commit()
                db.refresh(donation)
                processed.append(donation)
            except Exception as e:
                db.rollback()
                logger.error(f"Error approving donation {donation.donation_id}: {e}", exc_info=True)

    return processed


def scan_for_near_expiry(db: Session) -> List[DonationCandidate]:
    """
    Returns dynamically eligible donation candidates:
    - Dynamic status == DONATION (0 < remaining_hours <= 6)
    - stock_quantity > 0
    Expired products (remaining_hours <= 0) are strictly excluded.
    """
    process_pending_donations(db)

    candidates = []
    batches = (
        db.query(InventoryBatch, Product)
        .join(Product, InventoryBatch.product_id == Product.id)
        .filter(InventoryBatch.stock_quantity > 0)
        .all()
    )

    for batch, product in batches:
        exp_info = calculate_expiry_status(batch.expiry_date)
        status = exp_info["status"]
        rem_hours = exp_info["remaining_hours"]

        if status == "DONATION" and 0.0 < rem_hours <= 6.0:
            unit_price = product.mrp if product.mrp is not None else product.base_price
            val = Decimal(str(round(unit_price * batch.stock_quantity, 2)))

            candidates.append(
                DonationCandidate(
                    batch_id=batch.id,
                    sku=product.sku,
                    batch_number=batch.batch_number,
                    product_name=product.product_name,
                    category=product.category,
                    manufacturer=product.manufacturer,
                    stock_quantity=batch.stock_quantity,
                    base_price=product.base_price,
                    mrp=product.mrp,
                    expiry_date=batch.expiry_date,
                    remaining_hours=rem_hours,
                    remaining_days=exp_info["remaining_days"],
                    remaining_text=exp_info["remaining_text"],
                    daily_demand=batch.daily_demand,
                    estimated_value=val,
                    status=status,
                )
            )

    candidates.sort(key=lambda c: c.remaining_hours)
    return candidates


def create_donation_requests(
    db: Session, ngo_name: str, items: List[dict]
) -> List[NgoDonation]:
    """
    Creates PENDING donation requests for selected batches and quantities.
    Validates stock availability and donation status eligibility.
    Does NOT deduct stock immediately (simulates approval after 120 seconds).
    """
    if not items:
        raise ValueError("No donation items provided.")

    now_utc = datetime.now(timezone.utc)
    records = []

    for item in items:
        batch_id = item.get("batch_id")
        qty = item.get("quantity", 0)

        if not batch_id or qty <= 0:
            raise ValueError("Batch ID and positive donation quantity are required.")

        batch = db.query(InventoryBatch).filter(InventoryBatch.id == batch_id).first()
        if not batch:
            raise ValueError(f"Inventory batch {batch_id} not found.")

        if qty > batch.stock_quantity:
            b_label = batch.batch_number or batch_id
            raise ValueError(
                f"Donation quantity ({qty}) exceeds available stock ({batch.stock_quantity}) "
                f"for product '{batch.product.product_name}' (Batch: {b_label})."
            )

        exp_info = calculate_expiry_status(batch.expiry_date)
        if exp_info["status"] != "DONATION" or exp_info["remaining_hours"] <= 0:
            raise ValueError(
                f"Batch {batch.batch_number or batch_id} is not eligible for donation "
                f"(Status: {exp_info['status']}, Remaining: {exp_info['remaining_hours']}h)."
            )

        product = batch.product
        ts_str = now_utc.isoformat()
        raw_seed = f"{batch_id}-{ts_str}-{qty}".encode("utf-8")
        receipt_hash = hashlib.sha256(raw_seed).hexdigest()[:12].upper()
        receipt_ref = f"80G-{receipt_hash}"

        unit_price = product.mrp if product.mrp is not None else product.base_price
        val = float(Decimal(str(round(unit_price * qty, 2))))

        donation = NgoDonation(
            batch_id=batch.id,
            batch_number=batch.batch_number,
            sku=product.sku,
            ngo_name=ngo_name,
            product_name=product.product_name,
            quantity=qty,
            estimated_value=val,
            dispatch_timestamp=now_utc,
            requested_at=now_utc,
            approved_at=None,
            status="PENDING",
            tax_receipt_status="VERIFIED_80G",
            tax_receipt_reference=receipt_ref,
        )

        db.add(donation)
        records.append(donation)

    db.commit()
    for rec in records:
        db.refresh(rec)

    return records


def route_donation(db: Session, batch_id: int, ngo_name: str) -> NgoDonation:
    """
    Legacy endpoint adapter for single batch dispatch.
    """
    batch = db.query(InventoryBatch).filter(InventoryBatch.id == batch_id).first()
    if not batch:
        raise ValueError(f"InventoryBatch {batch_id} not found.")

    res = create_donation_requests(
        db, ngo_name=ngo_name, items=[{"batch_id": batch_id, "quantity": batch.stock_quantity}]
    )
    return res[0]
