import json
from unittest.mock import MagicMock, patch

import cv2
import httpx
import numpy as np
import pytest

from shelfguard.mistral_vision import (
    ImageProcessingError,
    MistralAPIError,
    MistralConfigError,
    MistralRateLimitError,
    MistralTimeoutError,
    calculate_relative_expiry,
    extract_product_information,
    get_mistral_model,
    normalize_date_string,
    normalize_raw_mistral_json,
    validate_and_preprocess_image,
)


def create_test_image(
    width: int = 800, height: int = 600, text: str = "ShelfGuard Packaging"
) -> bytes:
    """Helper to generate a clean synthetic product packaging image."""
    img = np.full((height, width, 3), 245, dtype=np.uint8)
    # Add border and header
    cv2.rectangle(img, (20, 20), (width - 20, height - 20), (20, 100, 30), 4)
    cv2.putText(
        img,
        text,
        (50, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        "BATCH: BG-9901 | PKD: 15/08/2026 | EXP: 15/08/2027",
        (50, 150),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (40, 40, 40),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        "MRP: Rs. 145.00 (Incl. of all taxes)",
        (50, 220),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (10, 10, 150),
        2,
        cv2.LINE_AA,
    )
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_model_configuration_default():
    """Validates that default Mistral model is ministral-14b-2512 and configurable."""
    with patch.dict("os.environ", {}, clear=True):
        model = get_mistral_model()
        assert model == "ministral-14b-2512"

    with patch.dict("os.environ", {"MISTRAL_MODEL": "ministral-custom-test"}):
        model = get_mistral_model()
        assert model == "ministral-custom-test"


def test_image_preprocessing_and_resizing():
    """Test resizing large phone camera images while preserving aspect ratio."""
    # 1. Large 3000x4000 image
    large_img = np.zeros((4000, 3000, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", large_img)
    large_bytes = buf.tobytes()

    opt_bytes, opt_mime, orig_dims, opt_dims = validate_and_preprocess_image(
        large_bytes, mime_type="image/jpeg", max_dim=1600
    )

    assert opt_mime == "image/jpeg"
    assert orig_dims == (3000, 4000)
    assert max(opt_dims) == 1600
    assert opt_dims == (1200, 1600)  # Preserved 3:4 aspect ratio
    assert len(opt_bytes) > 0

    # 2. Rejection of empty bytes
    with pytest.raises(ImageProcessingError):
        validate_and_preprocess_image(b"")

    # 3. Rejection of corrupted bytes
    with pytest.raises(ImageProcessingError):
        validate_and_preprocess_image(b"corrupt-data-not-image")

    # 4. Rejection of unsupported MIME types
    with pytest.raises(ImageProcessingError) as exc_info:
        validate_and_preprocess_image(large_bytes, mime_type="application/pdf")
    assert "Unsupported image format" in str(exc_info.value)


def test_date_normalization():
    """Test date parsing across various Indian packaging conventions."""
    # DD/MM/YYYY
    iso, raw = normalize_date_string("15/08/2026")
    assert iso == "2026-08-15"
    assert raw == "15/08/2026"

    # DD-MM-YYYY
    iso, _ = normalize_date_string("01-12-2027")
    assert iso == "2027-12-01"

    # YYYY-MM-DD
    iso, _ = normalize_date_string("2026-09-30")
    assert iso == "2026-09-30"

    # MM/YYYY (Should NOT invent a day)
    iso, raw = normalize_date_string("08/2027")
    assert iso is None
    assert raw == "08/2027"

    # Words: Aug 2027 (Should NOT invent a day)
    iso, raw = normalize_date_string("Aug 2027")
    assert iso is None
    assert raw == "Aug 2027"

    # Embedded in label: "PKD: 10/05/2026"
    iso, _ = normalize_date_string("PKD: 10/05/2026")
    assert iso == "2026-05-10"


def test_relative_expiry_calculation():
    """Test 'Best Before X Months From MFD' calculation."""
    # 6 months from 2026-08-15 -> 2027-02-15
    exp = calculate_relative_expiry("2026-08-15", 6)
    assert exp == "2027-02-15"

    # 12 months from 2026-01-01 -> 2027-01-01
    exp = calculate_relative_expiry("2026-01-01", 12)
    assert exp == "2027-01-01"

    # Missing MFD
    assert calculate_relative_expiry(None, 6) is None


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-mistral-key")
def test_successful_product_extraction(mock_key):
    """Test successful packaging extraction via Mistral Vision model."""
    mock_mistral_json = {
        "product_name": "Amul Pure Ghee 1L",
        "manufacturer": "Gujarat Co-operative Milk Marketing Federation Ltd.",
        "category": "Dairy Products",
        "batch_number": "B-GHEE-882",
        "manufacturing_date": "10/06/2026",
        "expiry_date": "10/06/2027",
        "mrp": "₹650.00",
        "base_cost_price": "650",
        "expiry_text": "EXP 10/06/2027",
        "confidence": {
            "product_name": 0.98,
            "manufacturer": 0.95,
            "category": 0.90,
            "batch_number": 0.96,
            "manufacturing_date": 0.94,
            "expiry_date": 0.97,
            "mrp": 0.98,
        },
        "warnings": [],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_mistral_json)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image(text="Amul Pure Ghee 1L")
        result = extract_product_information(img_bytes, mime_type="image/jpeg")

        assert result.success is True
        assert result.ocr_engine == "mistral-vision"
        assert result.semantic_engine == "mistral-vision"
        assert result.fallback_used is False
        assert result.product_name == "Amul Pure Ghee 1L"
        assert result.manufacturer == "Gujarat Co-operative Milk Marketing Federation Ltd."
        assert result.category == "Dairy Products"
        assert result.batch_number == "B-GHEE-882"
        assert result.manufacturing_date == "2026-06-10"
        assert result.expiry_date == "2027-06-10"
        assert result.mrp == 650.0
        assert result.base_price == 650.0
        assert result.confidence["product_name"] == 0.98
        assert result.confidence["expiry_date"] == 0.97
        assert result.overall_confidence >= 0.90


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-mistral-key")
def test_missing_fields_handling(mock_key):
    """Test handling of null / undetected fields without hallucinations."""
    mock_mistral_json = {
        "product_name": "Organic Tomatoes",
        "manufacturer": None,
        "category": "Fresh Produce",
        "batch_number": None,
        "manufacturing_date": None,
        "expiry_date": None,
        "mrp": None,
        "base_cost_price": None,
        "expiry_text": None,
        "confidence": {
            "product_name": 0.85,
            "category": 0.80,
        },
        "warnings": ["No batch number or expiry date visible on packaging."],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_mistral_json)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image(text="Organic Tomatoes")
        result = extract_product_information(img_bytes)

        assert result.product_name == "Organic Tomatoes"
        assert result.batch_number is None
        assert result.expiry_date is None
        assert result.mrp is None
        assert result.confidence["batch_number"] == 0.0
        assert result.confidence["expiry_date"] == 0.0
        assert any("Expiry date could not be confidently read" in w for w in result.warnings)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value=None)
def test_missing_api_key_error(mock_key):
    """Test missing MISTRAL_API_KEY error behavior."""
    img_bytes = create_test_image()
    with pytest.raises(MistralConfigError) as exc_info:
        extract_product_information(img_bytes)
    assert "MISTRAL_API_KEY is not configured" in str(exc_info.value)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="invalid-key")
def test_invalid_api_key_401(mock_key):
    """Test 401 Unauthorized response from Mistral."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid API key"

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image()
        with pytest.raises(MistralConfigError) as exc_info:
            extract_product_information(img_bytes)
        assert "Invalid or unauthorized Mistral API key" in str(exc_info.value)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_rate_limit_429_handling(mock_key):
    """Test 429 Rate Limit error from Mistral."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Too Many Requests"

    with patch("httpx.Client.post", return_value=mock_resp), patch("time.sleep"):
        img_bytes = create_test_image()
        with pytest.raises(MistralRateLimitError):
            extract_product_information(img_bytes)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_upstream_500_error_handling(mock_key):
    """Test 500 internal server error from Mistral."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.Client.post", return_value=mock_resp), patch("time.sleep"):
        img_bytes = create_test_image()
        with pytest.raises(MistralAPIError) as exc_info:
            extract_product_information(img_bytes)
        assert "Mistral Vision API server error (500)" in str(exc_info.value)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_timeout_handling(mock_key):
    """Test network timeout communicating with Mistral."""
    with (
        patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timeout")),
        patch("time.sleep"),
    ):
        img_bytes = create_test_image()
        with pytest.raises(MistralTimeoutError):
            extract_product_information(img_bytes)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_invalid_json_model_response(mock_key):
    """Test handling when model returns non-JSON text or malformed JSON."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Sorry, I am unable to extract information."}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image()
        with pytest.raises(MistralAPIError):
            extract_product_information(img_bytes)


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_mfd_with_best_before_duration_extraction(mock_key):
    """Test package with 'Best Before 6 Months From MFD' relative calculation."""
    mock_mistral_json = {
        "product_name": "Haldiram Bhujia 400g",
        "manufacturer": "Haldiram Snacks Pvt Ltd",
        "category": "Snacks & Namkeen",
        "batch_number": "NAM-441",
        "manufacturing_date": "2026-08-01",
        "expiry_date": None,
        "mrp": 95.0,
        "base_cost_price": 95.0,
        "expiry_text": "Best Before 6 Months From MFD",
        "confidence": {
            "product_name": 0.95,
            "manufacturing_date": 0.92,
        },
        "warnings": [],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_mistral_json)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image(text="Haldiram Bhujia 400g")
        result = extract_product_information(img_bytes)

        assert result.product_name == "Haldiram Bhujia 400g"
        assert result.manufacturing_date == "2026-08-01"
        assert result.expiry_date == "2027-02-01"
        assert any("Expiry date calculated as 2027-02-01" in w for w in result.warnings)


def test_normalize_raw_mistral_json_nested_structures():
    """Unit test for raw JSON normalization before Pydantic schema validation."""
    # Test 1: manufacturer with company and brand
    raw_pepsico = {
        "manufacturer": {
            "brand": "Pepsico",
            "company": "Pepsico India Holdings Pvt. Ltd.",
        },
        "product_name": {"name": "Lays Classic Salted"},
        "batch_number": {"value": "LOT12345"},
        "mrp": {"value": "₹50"},
        "confidence": {
            "expiry_date": {"score": 0.92},
            "product_name": 0.95,
        },
        "warnings": ["Small text detected."],
    }
    normalized = normalize_raw_mistral_json(raw_pepsico)
    assert normalized["manufacturer"] == "Pepsico India Holdings Pvt. Ltd."
    assert normalized["product_name"] == "Lays Classic Salted"
    assert normalized["batch_number"] == "LOT12345"
    assert normalized["mrp"] == 50.0
    assert normalized["confidence"]["expiry_date"] == 0.92
    assert normalized["confidence"]["product_name"] == 0.95
    assert normalized["warnings"] == ["Small text detected."]

    # Test 2: manufacturer with only brand
    raw_brand_only = {"manufacturer": {"brand": "Pepsico"}}
    normalized_brand = normalize_raw_mistral_json(raw_brand_only)
    assert normalized_brand["manufacturer"] == "Pepsico"

    # Test 3: manufacturer as string
    raw_str = {"manufacturer": "Nestle India"}
    normalized_str = normalize_raw_mistral_json(raw_str)
    assert normalized_str["manufacturer"] == "Nestle India"

    # Test 4: null and unexpected types
    raw_null = {"manufacturer": None, "product_name": None}
    normalized_null = normalize_raw_mistral_json(raw_null)
    assert normalized_null["manufacturer"] is None
    assert normalized_null["product_name"] is None


@patch("shelfguard.mistral_vision._find_mistral_api_key", return_value="fake-key")
def test_end_to_end_extraction_with_nested_pepsico_response(mock_key):
    """End-to-end extraction test with exact Pepsico dictionary structure."""
    mock_mistral_nested_json = {
        "product_name": {"name": "Lays Classic Salted 50g"},
        "manufacturer": {
            "brand": "Pepsico",
            "company": "Pepsico India Holdings Pvt. Ltd.",
        },
        "category": {"name": "Chips & Crisps"},
        "batch_number": {"value": "LOT-LAY-99"},
        "manufacturing_date": {"date": "10/08/2026"},
        "expiry_date": {"date": "10/02/2027"},
        "mrp": {"value": "MRP ₹20.00"},
        "base_cost_price": {"value": "20.00"},
        "confidence": {
            "product_name": {"score": 0.95},
            "manufacturer": {"score": 0.90},
            "expiry_date": {"score": 0.92},
        },
        "warnings": [],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_mistral_nested_json)}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        img_bytes = create_test_image(text="Lays Classic Salted")
        result = extract_product_information(img_bytes)

        assert result.success is True
        assert result.manufacturer == "Pepsico India Holdings Pvt. Ltd."
        assert result.product_name == "Lays Classic Salted 50g"
        assert result.category == "Chips & Crisps"
        assert result.batch_number == "LOT-LAY-99"
        assert result.manufacturing_date == "2026-08-10"
        assert result.expiry_date == "2027-02-10"
        assert result.mrp == 20.0
        assert result.base_price == 20.0
        assert result.confidence["expiry_date"] == 0.92
        assert result.confidence["product_name"] == 0.95

