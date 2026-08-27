import os
import sys

sys.path.insert(0, os.path.abspath("src"))
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shelfguard.config import settings
from shelfguard.database import Inventory, NgoDonation
from shelfguard.ngo_router import route_donation, scan_for_near_expiry


def run_manual_verification():
    print("Starting Manual Verification...")

    # 1. Setup session
    engine = create_engine(settings.db_path)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Clean up old test data
    db.query(NgoDonation).filter(NgoDonation.sku == "MANUAL-TEST-SKU").delete()
    db.query(Inventory).filter(Inventory.sku == "MANUAL-TEST-SKU").delete()
    db.commit()

    # 2. Insert Candidate
    now = datetime.now(timezone.utc)
    # Target exactly 1 day from now so the end of that day is between 24-48 hours
    target_dt = now + timedelta(days=1)

    item = Inventory(
        sku="MANUAL-TEST-SKU",
        product_name="Manual Verification Item",
        category="Test Category",
        base_price=25.0,
        stock_quantity=10,
        expiry_date=target_dt.strftime("%Y-%m-%d"),
        daily_demand=1,  # Below threshold
        status="ACTIVE",
    )
    db.add(item)
    db.commit()
    print("[OK] Inserted candidate item into database")

    # 3. Candidate Discovery
    print(f"DEBUG: Using NGO threshold: {settings.ngo_daily_demand_threshold}")
    candidates = scan_for_near_expiry(db)
    found = any(c.sku == "MANUAL-TEST-SKU" for c in candidates)
    if found:
        print("[OK] Candidate discovery found the test SKU")
    else:
        for item in db.query(Inventory).filter(Inventory.sku == "MANUAL-TEST-SKU").all():
            print(
                f"DEBUG item in DB: status={item.status}, stock={item.stock_quantity}, "
                f"demand={item.daily_demand}, expiry={item.expiry_date}"
            )
            from shelfguard.ngo_router import parse_inventory_date

            pd = parse_inventory_date(item.expiry_date)
            rh = (pd - now).total_seconds() / 3600.0 if pd else -1
            print(f"DEBUG parsed={pd}, remaining={rh}h")
        print("[FAIL] Candidate discovery did not find the test SKU!")
        sys.exit(1)

    # 4. Successful Dispatch
    try:
        settings.ngo_partners = ["Feeding India"]
        settings.ngo_daily_demand_threshold = 5
        record = route_donation(db, sku="MANUAL-TEST-SKU", ngo_name="Feeding India")
        print(f"[OK] Dispatched item. Receipt: {record.tax_receipt_reference}")
    except Exception as e:
        print(f"[FAIL] Dispatch failed: {e}")
        sys.exit(1)

    # 5. Inventory Status Transition
    item = db.query(Inventory).filter(Inventory.sku == "MANUAL-TEST-SKU").first()
    if item.status == "NGO_DISPATCH":
        print("[OK] Inventory status correctly transitioned to NGO_DISPATCH")
    else:
        print(f"[FAIL] Inventory status is {item.status}")

    # 6. Donation Record Creation
    donations = db.query(NgoDonation).filter(NgoDonation.sku == "MANUAL-TEST-SKU").all()
    if len(donations) == 1:
        print("[OK] Exactly one donation history record found")
        assert donations[0].estimated_value == 250.0
        print("[OK] Estimated value is correctly calculated as 250.0")
    else:
        print(f"[FAIL] Expected 1 donation record, found {len(donations)}")

    # 7. Duplicate Dispatch Rejection
    try:
        route_donation(db, sku="MANUAL-TEST-SKU", ngo_name="Feeding India")
        print("[FAIL] Duplicate dispatch was incorrectly allowed!")
    except ValueError as e:
        print(f"[OK] Duplicate dispatch rejected as expected: {e}")

    # Cleanup
    db.query(NgoDonation).filter(NgoDonation.sku == "MANUAL-TEST-SKU").delete()
    db.query(Inventory).filter(Inventory.sku == "MANUAL-TEST-SKU").delete()
    db.commit()
    db.close()

    print("Manual Verification Complete.")


if __name__ == "__main__":
    run_manual_verification()
