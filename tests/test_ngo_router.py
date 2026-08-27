from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shelfguard.database import (
    BUSINESS_TIMEZONE,
    Base,
    InventoryBatch,
    Product,
    calculate_expiry_status,
)
from shelfguard.ngo_router import (
    create_donation_requests,
    process_pending_donations,
    scan_for_near_expiry,
)

# In-memory test database
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    product = Product(
        sku="NGO-TEST-SKU",
        product_name="Test Perishable Product",
        category="Perishable",
        manufacturer="Fresh Farm",
        base_price=10.0,
        mrp=15.0,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    now_kolkata = datetime.now(BUSINESS_TIMEZONE)

    # 1. DONATION batch: expiring in 3 hours
    dt_3h = (now_kolkata + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    b_donation = InventoryBatch(
        product_id=product.id,
        batch_number="B-DONATION",
        internal_batch_id="INT-DONATION-1",
        expiry_date=dt_3h,
        stock_quantity=100,
        daily_demand=5,
        status="ACTIVE",
    )
    db.add(b_donation)

    # 2. CRITICAL batch: expiring in 24 hours
    dt_24h = (now_kolkata + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    b_critical = InventoryBatch(
        product_id=product.id,
        batch_number="B-CRITICAL",
        internal_batch_id="INT-CRITICAL-1",
        expiry_date=dt_24h,
        stock_quantity=50,
        daily_demand=5,
        status="ACTIVE",
    )
    db.add(b_critical)

    # 3. EXPIRED batch: expired 2 hours ago
    dt_exp = (now_kolkata - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    b_expired = InventoryBatch(
        product_id=product.id,
        batch_number="B-EXPIRED",
        internal_batch_id="INT-EXPIRED-1",
        expiry_date=dt_exp,
        stock_quantity=30,
        daily_demand=0,
        status="ACTIVE",
    )
    db.add(b_expired)

    db.commit()
    yield
    db.close()


def test_calculate_expiry_status_logic():
    now = datetime.now(BUSINESS_TIMEZONE)

    # SAFE: > 168 hours
    exp_10d = (now + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_10d, ref_time=now)
    assert res["status"] == "SAFE"

    # NEAR_EXPIRY: 48 < remaining <= 168
    exp_5d = (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_5d, ref_time=now)
    assert res["status"] == "NEAR_EXPIRY"

    # CRITICAL: 6 < remaining <= 48
    exp_24h = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_24h, ref_time=now)
    assert res["status"] == "CRITICAL"

    # DONATION: 0 < remaining <= 6
    exp_5h = (now + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_5h, ref_time=now)
    assert res["status"] == "DONATION"

    exp_1h = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_1h, ref_time=now)
    assert res["status"] == "DONATION"

    # EXPIRED: <= 0 hours
    exp_past = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    res = calculate_expiry_status(exp_past, ref_time=now)
    assert res["status"] == "EXPIRED"


def test_calculate_expiry_status_boundaries():
    now = datetime.now(BUSINESS_TIMEZONE)

    # Exactly 168 hours
    exp_168_str = (now + timedelta(hours=168)).strftime("%Y-%m-%d %H:%M:%S")
    res_168 = calculate_expiry_status(exp_168_str, ref_time=now)
    assert res_168["status"] == "NEAR_EXPIRY"

    # Exactly 48 hours
    exp_48_str = (now + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    res_48 = calculate_expiry_status(exp_48_str, ref_time=now)
    assert res_48["status"] == "CRITICAL"

    # Exactly 6 hours
    exp_6_str = (now + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    res_6 = calculate_expiry_status(exp_6_str, ref_time=now)
    assert res_6["status"] == "DONATION"

    # Just below 0 (-0.01 hours)
    exp_sub0_str = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    res_sub0 = calculate_expiry_status(exp_sub0_str, ref_time=now)
    assert res_sub0["status"] == "EXPIRED"


def test_scan_for_near_expiry_only_donation_candidates():
    db = TestingSessionLocal()
    candidates = scan_for_near_expiry(db)

    # Only B-DONATION should appear (B-CRITICAL and B-EXPIRED are excluded)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.batch_number == "B-DONATION"
    assert c.status == "DONATION"
    assert 0.0 < c.remaining_hours <= 6.0
    db.close()


def test_create_donation_request_pending():
    db = TestingSessionLocal()
    b_query = db.query(InventoryBatch).filter(InventoryBatch.batch_number == "B-DONATION")
    b_donation = b_query.first()
    assert b_donation is not None

    # Create partial donation (40 units out of 100)
    items = [{"batch_id": b_donation.id, "quantity": 40}]
    records = create_donation_requests(db, ngo_name="Feeding India (Zomato)", items=items)

    assert len(records) == 1
    rec = records[0]
    assert rec.status == "PENDING"
    assert rec.quantity == 40
    assert rec.ngo_name == "Feeding India (Zomato)"
    assert rec.approved_at is None

    # Stock is NOT yet deducted in PENDING state
    db.refresh(b_donation)
    assert b_donation.stock_quantity == 100
    db.close()


def test_donation_insufficient_stock_rejection():
    db = TestingSessionLocal()
    b_query = db.query(InventoryBatch).filter(InventoryBatch.batch_number == "B-DONATION")
    b_donation = b_query.first()
    assert b_donation is not None

    # Request 150 units when stock is only 100
    items = [{"batch_id": b_donation.id, "quantity": 150}]
    with pytest.raises(ValueError, match="exceeds available stock"):
        create_donation_requests(db, ngo_name="Food Bank Alliance", items=items)
    db.close()


def test_donation_approval_simulation_and_single_stock_deduction():
    db = TestingSessionLocal()
    b_query = db.query(InventoryBatch).filter(InventoryBatch.batch_number == "B-DONATION")
    b_donation = b_query.first()
    assert b_donation is not None

    items = [{"batch_id": b_donation.id, "quantity": 40}]
    records = create_donation_requests(db, ngo_name="Robin Hood Army", items=items)
    rec = records[0]

    # Manually backdate requested_at to 125 seconds ago to simulate time passing
    rec.requested_at = datetime.now(timezone.utc) - timedelta(seconds=125)
    db.commit()

    # Process pending donations
    processed = process_pending_donations(db)
    assert len(processed) == 1
    assert processed[0].status == "APPROVED"
    assert processed[0].approved_at is not None

    # Stock must now be deducted from 100 -> 60
    db.refresh(b_donation)
    assert b_donation.stock_quantity == 60

    # Processing again should NOT double-deduct (idempotency test)
    processed_again = process_pending_donations(db)
    assert len(processed_again) == 0
    db.refresh(b_donation)
    assert b_donation.stock_quantity == 60
    db.close()
