import io
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shelfguard.database import Base, InventoryBatch, Product, get_db
from shelfguard.main import app
from shelfguard.schemas import OcrExtractionResult

# Setup test DB
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = override_get_db
    with patch("joblib.load") as mock_load, patch("builtins.open"):
        # Configure mock model
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.50]
        mock_load.return_value = mock_model

        expected_cols = ["remaining_hours", "base_price", "initial_quantity", "daily_demand"]
        with patch("json.load", return_value=expected_cols):
            with TestClient(app) as c:
                yield c


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    product = Product(
        sku="TEST-123",
        product_name="Test Product",
        category="Test Category",
        manufacturer="Test Brand",
        base_price=10.0,
        mrp=15.0,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    batch = InventoryBatch(
        product_id=product.id,
        batch_number="B-001",
        internal_batch_id="BATCH-TEST-123-B-001",
        manufacturing_date="2026-01-01",
        expiry_date="2027-01-01",
        stock_quantity=250,
        daily_demand=5,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    db.commit()
    db.close()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_inventory_list(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1
    item = next(i for i in data["items"] if i["sku"] == "TEST-123")
    assert item["product_name"] == "Test Product"
    assert item["batch_number"] == "B-001"
    assert item["stock_quantity"] == 250
    assert item["mrp"] == 15.0


def test_get_inventory_detail(client):
    response = client.get("/inventory/TEST-123")
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "TEST-123"
    assert len(data["batches"]) == 1
    assert data["batches"][0]["stock_quantity"] == 250


def test_get_inventory_not_found(client):
    response = client.get("/inventory/NONEXISTENT-SKU")
    assert response.status_code == 404


@patch("shelfguard.main.extract_product_information")
def test_ocr_upload_valid(mock_extract, client):
    mock_extract.return_value = OcrExtractionResult(
        product_name="Sample Beverage",
        manufacturer="Fresh Bottlers",
        expiry_date="2027-06-30",
        manufacturing_date="2026-06-30",
        batch_number="LOT-990",
        mrp=45.0,
        base_price=45.0,
        raw_text="Sample text",
        confidence={"product_name": 0.9},
    )

    file_content = b"fake image bytes"
    files = {"image": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    response = client.post("/ocr/scan", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["product_name"] == "Sample Beverage"
    assert data["expiry_date"] == "2027-06-30"
    assert data["mrp"] == 45.0


def test_ocr_upload_no_images(client):
    response = client.post("/ocr/scan")
    assert response.status_code == 422


def test_ocr_upload_invalid_mime(client):
    files = {"image": ("test.txt", io.BytesIO(b"not image"), "text/plain")}
    response = client.post("/ocr/scan", files=files)
    assert response.status_code == 400


def test_create_batch_new_product(client):
    payload = {
        "sku": "NEW-PROD-SKU",
        "product_name": "New Cereal",
        "manufacturer": "GrainCorp",
        "expiry_date": "2027-12-31",
        "batch_number": "BATCH-C1",
        "stock_quantity": 250,
        "mrp": 120.0,
    }
    response = client.post("/inventory/batches", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["stock_quantity"] == 250
    assert data["batch_number"] == "BATCH-C1"

    # Verify inventory
    inv_res = client.get("/inventory/NEW-PROD-SKU")
    assert inv_res.status_code == 200
    batches = inv_res.json()["batches"]
    assert len(batches) == 1
    assert batches[0]["stock_quantity"] == 250


def test_create_batch_detect_existing_409(client):
    # Try creating batch matching existing TEST-123 with B-001
    payload = {
        "sku": "TEST-123",
        "product_name": "Test Product",
        "expiry_date": "2027-01-01",
        "batch_number": "B-001",
        "stock_quantity": 50,
    }
    response = client.post("/inventory/batches", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert "existing_batch" in data
    assert data["existing_batch"]["stock_quantity"] == 250


def test_create_batch_confirm_add_stock(client):
    # Confirm adding stock to existing batch B-001 (250 + 50 = 300)
    payload = {
        "sku": "TEST-123",
        "product_name": "Test Product",
        "expiry_date": "2027-01-01",
        "batch_number": "B-001",
        "stock_quantity": 50,
        "confirm_existing": True,
    }
    response = client.post("/inventory/batches", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["stock_quantity"] == 300

    # Ensure only 1 batch exists
    inv_res = client.get("/inventory/TEST-123")
    batches = inv_res.json()["batches"]
    assert len(batches) == 1
    assert batches[0]["stock_quantity"] == 300


def test_create_batch_force_new_batch(client):
    # Force new batch for same product and batch number
    payload = {
        "sku": "TEST-123",
        "product_name": "Test Product",
        "expiry_date": "2027-01-01",
        "batch_number": "B-001",
        "stock_quantity": 40,
        "force_new_batch": True,
    }
    response = client.post("/inventory/batches", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["stock_quantity"] == 40

    # Now 2 batches should exist
    inv_res = client.get("/inventory/TEST-123")
    batches = inv_res.json()["batches"]
    assert len(batches) == 2


def test_create_second_batch_different_expiry(client):
    # Same product, different expiry date -> created as second batch
    payload = {
        "sku": "TEST-123",
        "product_name": "Test Product",
        "expiry_date": "2028-05-15",
        "batch_number": "B-002",
        "stock_quantity": 100,
    }
    response = client.post("/inventory/batches", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["stock_quantity"] == 100
    assert data["batch_number"] == "B-002"

    inv_res = client.get("/inventory/TEST-123")
    batches = inv_res.json()["batches"]
    assert len(batches) >= 2


def test_create_batch_validation_failures(client):
    # 1. Zero/Negative stock
    r1 = client.post(
        "/inventory/batches",
        json={"product_name": "Bad Product", "expiry_date": "2027-01-01", "stock_quantity": 0},
    )
    assert r1.status_code == 422

    # 2. Invalid date format
    r2 = client.post(
        "/inventory/batches",
        json={
            "product_name": "Bad Product",
            "expiry_date": "31-12-2027",  # Not ISO YYYY-MM-DD
            "stock_quantity": 10,
        },
    )
    assert r2.status_code == 422

    # 3. Manufacturing date > Expiry date
    r3 = client.post(
        "/inventory/batches",
        json={
            "product_name": "Bad Product",
            "manufacturing_date": "2028-01-01",
            "expiry_date": "2027-01-01",
            "stock_quantity": 10,
        },
    )
    assert r3.status_code == 422
    assert "cannot be later than expiry" in r3.json()["detail"].lower()


def test_pricing_recommend_valid(client):
    payload = {
        "remaining_hours": 24.0,
        "base_price": 10.0,
        "initial_quantity": 50,
        "daily_demand": 5,
    }
    response = client.post("/pricing/recommend", json=payload)
    assert response.status_code == 200
    assert response.json()["recommended_discount"] == 0.50


def test_tax_calculate_valid(client):
    payload = {"taxable_amount": "100.00", "tax_rate": "0.05"}
    response = client.post("/tax/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tax_collected"] == "5.00"


def test_phase9_dashboard_stats(client):
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_inventory_items" in data
    assert "safe_count" in data
    assert "near_expiry_count" in data
    assert "critical_count" in data
    assert "donation_count" in data
    assert "expired_count" in data
    assert "ngo_candidates" in data


def test_phase9_inventory_filtering_and_search(client):
    # Test search by product name
    r1 = client.get("/inventory?search=Test Product")
    assert r1.status_code == 200
    assert r1.json()["total"] >= 1

    # Test status filter
    r2 = client.get("/inventory?status=SAFE")
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert all(item["status"] == "SAFE" for item in items)


def test_phase9_ngo_donation_api_flow(client):
    db = TestingSessionLocal()
    from datetime import timedelta

    from shelfguard.database import BUSINESS_TIMEZONE

    now_kolkata = datetime.now(BUSINESS_TIMEZONE)
    dt_3h = (now_kolkata + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    # Add a donation candidate batch directly to test DB
    product = db.query(Product).filter(Product.sku == "TEST-123").first()
    don_batch = InventoryBatch(
        product_id=product.id,
        batch_number="B-DONATE-API",
        internal_batch_id="INT-DONATE-API-1",
        expiry_date=dt_3h,
        stock_quantity=80,
        daily_demand=2,
        status="ACTIVE",
    )
    db.add(don_batch)
    db.commit()
    batch_id = don_batch.id
    db.close()

    # 1. Fetch candidates
    c_res = client.get("/api/ngo/candidates")
    assert c_res.status_code == 200
    candidates = c_res.json()
    target = next((c for c in candidates if c["batch_id"] == batch_id), None)
    assert target is not None
    assert target["status"] == "DONATION"

    # 2. Submit donation request
    req_payload = {
        "ngo_name": "Food Bank Alliance",
        "items": [{"batch_id": batch_id, "quantity": 30}],
    }
    sub_res = client.post("/api/ngo/request", json=req_payload)
    assert sub_res.status_code == 200
    donations = sub_res.json()
    assert len(donations) == 1
    assert donations[0]["status"] == "PENDING"
    assert donations[0]["quantity"] == 30

    # 3. Check donation history
    hist_res = client.get("/api/ngo/donations")
    assert hist_res.status_code == 200
    history = hist_res.json()
    hist_item = next((h for h in history if h["batch_id"] == batch_id), None)
    assert hist_item is not None
    assert hist_item["status"] == "PENDING"
    assert hist_item["remaining_seconds_to_approve"] > 0


def test_phase10_dynamic_pricing_integration(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0

    item = data["items"][0]
    assert "dynamic_discount_percent" in item
    assert "dynamic_discount_fraction" in item
    assert "final_price" in item
    assert "is_override" in item


def test_phase10_pricing_recommend_consistency(client):
    payload = {
        "remaining_hours": 48.0,
        "base_price": 200.0,
        "initial_quantity": 30,
        "daily_demand": 5,
    }
    response = client.post("/pricing/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "recommended_discount" in data
    assert "dynamic_discount_percent" in data
    assert "final_price" in data
    assert data["dynamic_discount_percent"] == 50.0
    assert data["final_price"] == 100.0


def test_dashboard_categories_endpoint(client):
    response = client.get("/api/dashboard/categories")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total_batches" in data
    assert "total_categories" in data
    assert data["total_batches"] >= 1
    assert data["total_categories"] >= 1
    assert any(i["category"] == "Test Category" for i in data["items"])
    assert data["items"][0]["percentage"] > 0.0


def test_dashboard_trends_endpoint(client):
    response = client.get("/api/dashboard/trends")
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert "labels" in data
    assert "discount_rates" in data
    assert "demand_velocities" in data
    assert len(data["labels"]) == 5
    assert len(data["discount_rates"]) == 5
    assert len(data["demand_velocities"]) == 5
    assert "summary_insight" in data
    # Test batch in setup_db has expiry in 2027 (> 168h -> SAFE)
    safe_stage = next(s for s in data["stages"] if s["stage_key"] == "SAFE")
    assert safe_stage["batch_count"] >= 1


def test_dashboard_dynamic_update_when_batch_added(client):
    # Initial state
    cat_res1 = client.get("/api/dashboard/categories")
    assert cat_res1.status_code == 200
    init_total = cat_res1.json()["total_batches"]

    # Add a new batch in Bakery category
    new_batch_payload = {
        "sku": "BAKERY-001",
        "product_name": "Artisan Bread",
        "category": "Bakery",
        "manufacturer": "Local Bakers",
        "batch_number": "B-BAKE-99",
        "manufacturing_date": "2026-08-01",
        "expiry_date": "2026-09-01",
        "stock_quantity": 40,
        "mrp": 60.0,
        "base_price": 50.0,
        "daily_demand": 8,
    }
    create_res = client.post("/inventory/batches", json=new_batch_payload)
    assert create_res.status_code == 200

    # Verify categories endpoint immediately reflects the newly added category and increased total
    cat_res2 = client.get("/api/dashboard/categories")
    assert cat_res2.status_code == 200
    updated_data = cat_res2.json()
    assert updated_data["total_batches"] == init_total + 1
    bakery_item = next((i for i in updated_data["items"] if i["category"] == "Bakery"), None)
    assert bakery_item is not None
    assert bakery_item["count"] == 1
    assert bakery_item["total_stock_units"] == 40


