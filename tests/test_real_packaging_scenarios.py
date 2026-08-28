import io
import json
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shelfguard.main import app
from shelfguard.mistral_vision import (
    MistralAPIError,
    MistralRateLimitError,
    extract_product_information,
    validate_and_preprocess_image,
)
from shelfguard.schemas import OcrExtractionResult


def create_packaging_image(
    title: str,
    batch: str = "B-9901",
    mfg: str = "15/08/2026",
    exp: str = "15/08/2027",
    mrp: str = "Rs. 145.00",
    blur: bool = False,
    width: int = 1200,
    height: int = 900,
) -> bytes:
    img = np.full((height, width, 3), 245, dtype=np.uint8)
    cv2.rectangle(img, (30, 30), (width - 30, height - 30), (20, 120, 40), 4)
    cv2.putText(img, title, (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
    if batch:
        cv2.putText(
            img, f"Batch: {batch}", (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 40), 2
        )
    if mfg:
        cv2.putText(
            img, f"PKD: {mfg}", (60, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 40), 2
        )
    if exp:
        cv2.putText(
            img, f"EXP: {exp}", (60, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 40), 2
        )
    if mrp:
        cv2.putText(
            img, f"MRP: {mrp}", (60, 440), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 180), 2
        )

    if blur:
        img = cv2.GaussianBlur(img, (25, 25), 0)

    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_1_clear_indian_food_product(mock_key):
    """Scenario 1: Clear Indian Food packaging (Tata Tea Gold)."""
    mock_json = {
        "product_name": "Tata Tea Gold 500g",
        "manufacturer": "Tata Consumer Products Ltd",
        "category": "Beverages & Tea",
        "batch_number": "TTG-2026-X1",
        "manufacturing_date": "15/07/2026",
        "expiry_date": "15/07/2027",
        "mrp": "₹340.00",
        "base_cost_price": "340.00",
        "expiry_text": "EXP 15/07/2027",
        "confidence": {
            "product_name": 0.98,
            "manufacturer": 0.95,
            "category": 0.92,
            "batch_number": 0.96,
            "manufacturing_date": 0.95,
            "expiry_date": 0.97,
            "mrp": 0.98,
        },
        "warnings": [],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_packaging_image("Tata Tea Gold 500g", mrp="Rs. 340.00")
        result = extract_product_information(img_bytes)
        assert result.product_name == "Tata Tea Gold 500g"
        assert result.manufacturer == "Tata Consumer Products Ltd"
        assert result.category == "Beverages & Tea"
        assert result.expiry_date == "2027-07-15"
        assert result.mrp == 340.0


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_2_blurry_image(mock_key):
    """Scenario 2: Blurry image where text cannot be confidently extracted."""
    mock_json = {
        "product_name": None,
        "manufacturer": None,
        "category": None,
        "batch_number": None,
        "manufacturing_date": None,
        "expiry_date": None,
        "mrp": None,
        "base_cost_price": None,
        "expiry_text": None,
        "confidence": {},
        "warnings": ["Image is excessively blurry. Packaging text could not be resolved."],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        blurry_bytes = create_packaging_image("Blurry Product", blur=True)
        result = extract_product_information(blurry_bytes)
        assert result.product_name is None
        assert result.expiry_date is None
        assert result.overall_confidence == 0.0
        assert any("Expiry date could not be confidently read" in w for w in result.warnings)


def test_scenario_3_large_phone_camera_image():
    """Scenario 3: 4000x3000 large high-res phone image resized intelligently."""
    large_bytes = create_packaging_image("Large Phone Camera Image", width=3000, height=4000)
    opt_bytes, opt_mime, orig_dims, opt_dims = validate_and_preprocess_image(large_bytes)
    assert orig_dims == (3000, 4000)
    assert max(opt_dims) == 1600
    assert opt_dims == (1200, 1600)
    assert opt_mime == "image/jpeg"


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_4_expiry_date_visible(mock_key):
    """Scenario 4: Packaging with clear expiry date."""
    mock_json = {
        "product_name": "Aashirvaad Superior MP Atta",
        "manufacturer": "ITC Limited",
        "category": "Atta & Flours",
        "batch_number": "AASH-99",
        "manufacturing_date": "2026-08-10",
        "expiry_date": "2027-02-10",
        "mrp": 250.0,
        "base_cost_price": 250.0,
        "confidence": {"product_name": 0.95, "expiry_date": 0.95},
        "warnings": [],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_packaging_image("Aashirvaad Superior MP Atta")
        res = extract_product_information(img_bytes)
        assert res.expiry_date == "2027-02-10"


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_5_expiry_date_not_visible(mock_key):
    """Scenario 5: Packaging where expiry date is missing/cut off."""
    mock_json = {
        "product_name": "Loose Basmati Rice 5kg",
        "manufacturer": "India Gate",
        "category": "Rice & Grains",
        "batch_number": "BATCH-01",
        "manufacturing_date": None,
        "expiry_date": None,
        "mrp": 450.0,
        "base_cost_price": 450.0,
        "confidence": {"product_name": 0.9, "mrp": 0.9},
        "warnings": ["Expiry date not found on visible packaging surface."],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_packaging_image("Basmati Rice", exp="")
        res = extract_product_information(img_bytes)
        assert res.expiry_date is None
        assert any("Expiry date could not be confidently read" in w for w in res.warnings)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_6_mfd_plus_best_before_duration(mock_key):
    """Scenario 6: MFD + 'Best Before 9 Months From MFD' calculation."""
    mock_json = {
        "product_name": "Maggi 2-Minute Noodles",
        "manufacturer": "Nestle India",
        "category": "Instant Noodles",
        "batch_number": "MAG-8821",
        "manufacturing_date": "10/05/2026",
        "expiry_date": None,
        "mrp": 14.0,
        "base_cost_price": 14.0,
        "expiry_text": "Best Before 9 Months from Manufacturing",
        "confidence": {"product_name": 0.95, "manufacturing_date": 0.92},
        "warnings": [],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_packaging_image("Maggi 2-Minute Noodles")
        res = extract_product_information(img_bytes)
        assert res.manufacturing_date == "2026-05-10"
        assert res.expiry_date == "2027-02-10"
        assert any("Expiry date calculated as 2027-02-10" in w for w in res.warnings)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_7_and_8_mrp_and_batch_number(mock_key):
    """Scenarios 7 & 8: Explicit MRP and Batch Number extraction."""
    mock_json = {
        "product_name": "Dabur Honey 500g",
        "manufacturer": "Dabur India Ltd",
        "category": "Packaged Foods",
        "batch_number": "LOT-DH-9002",
        "manufacturing_date": "2026-01-15",
        "expiry_date": "2027-01-15",
        "mrp": "Rs. 235.00",
        "base_cost_price": "235.00",
        "confidence": {"product_name": 0.95, "batch_number": 0.95, "mrp": 0.95},
        "warnings": [],
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(mock_json)}}]}

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_packaging_image(
            "Dabur Honey 500g", batch="LOT-DH-9002", mrp="Rs. 235.00"
        )
        res = extract_product_information(img_bytes)
        assert res.batch_number == "LOT-DH-9002"
        assert res.mrp == 235.0
        assert res.base_price == 235.0


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_9_api_failure(mock_key):
    """Scenario 9: Upstream API 500 failure."""
    mock_resp = MagicMock(status_code=500, text="Internal Server Error")
    with patch("httpx.Client.post", return_value=mock_resp), patch("time.sleep"):
        img_bytes = create_packaging_image("Product Test")
        with pytest.raises(MistralAPIError):
            extract_product_information(img_bytes)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_scenario_10_rate_limit_handling(mock_key):
    """Scenario 10: 429 Rate limit handling."""
    mock_resp = MagicMock(status_code=429, text="Too Many Requests")
    with patch("httpx.Client.post", return_value=mock_resp), patch("time.sleep"):
        img_bytes = create_packaging_image("Product Test")
        with pytest.raises(MistralRateLimitError):
            extract_product_information(img_bytes)


@patch("shelfguard.main.extract_product_information")
def test_scenario_11_and_12_frontend_population_and_manual_correction(mock_extract):
    """Scenarios 11 & 12: Endpoint returns schema matching frontend form population and batch."""
    mock_extract.return_value = OcrExtractionResult(
        success=True,
        ocr_engine="mistral-vision",
        semantic_engine="mistral-vision",
        product_name="Haldiram Gulab Jamun 1kg",
        manufacturer="Haldiram Foods International",
        category="Sweets & Desserts",
        batch_number="GJ-110",
        manufacturing_date="2026-08-01",
        expiry_date="2027-08-01",
        mrp=260.0,
        base_price=260.0,
        confidence={"product_name": 0.95, "expiry_date": 0.95},
    )

    cols = ["remaining_hours", "base_price", "initial_quantity", "daily_demand"]
    with (
        patch("joblib.load"),
        patch("builtins.open"),
        patch("json.load", return_value=cols),
    ):
        with TestClient(app) as client:
            img_bytes = create_packaging_image("Gulab Jamun")
            scan_res = client.post(
                "/ocr/scan",
                files={"image": ("packaging.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            )
            assert scan_res.status_code == 200
            data = scan_res.json()
            assert data["product_name"] == "Haldiram Gulab Jamun 1kg"
            assert data["expiry_date"] == "2027-08-01"
            assert data["mrp"] == 260.0

            # Test user manual verification & inventory batch creation
            batch_payload = {
                "product_name": data["product_name"],
                "manufacturer": data["manufacturer"],
                "category": data["category"],
                "batch_number": data["batch_number"],
                "manufacturing_date": data["manufacturing_date"],
                "expiry_date": data["expiry_date"],
                "mrp": data["mrp"],
                "base_price": data["base_price"],
                "stock_quantity": 40,  # Manually entered by user
            }
            create_res = client.post("/inventory/batches", json=batch_payload)
            assert create_res.status_code == 200
            batch_data = create_res.json()
            assert batch_data["stock_quantity"] == 40
            assert batch_data["expiry_date"] == "2027-08-01"
