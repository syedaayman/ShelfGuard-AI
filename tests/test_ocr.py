from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from shelfguard.ocr_engine import (
    ImageProcessingError,
    _extract_structured_fields,
    _get_easyocr_reader,
    _preprocess_image,
    extract_product_data,
    validate_and_optimize_image,
)
from shelfguard.semantic_extractor import (
    SemanticExtractionError,
    SemanticRateLimitError,
)


def test_image_preprocessing_pipeline():
    # 1. Valid dummy image
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    valid_bytes = buf.tobytes()

    proc = _preprocess_image(valid_bytes)
    assert isinstance(proc, np.ndarray)
    assert len(proc.shape) == 2  # Grayscale

    # 2. Empty bytes
    with pytest.raises(ImageProcessingError):
        _preprocess_image(b"")

    # 3. Corrupt bytes
    with pytest.raises(ImageProcessingError):
        _preprocess_image(b"not-an-image-data-corrupt")

    # 4. Oversized image resizing
    large_img = np.zeros((2000, 3000, 3), dtype=np.uint8)
    _, large_buf = cv2.imencode(".jpg", large_img)
    proc_large = _preprocess_image(large_buf.tobytes())
    assert max(proc_large.shape[:2]) <= 1600


def test_validate_and_optimize_image_scaling_and_compression():
    large_img = np.zeros((2400, 3200, 3), dtype=np.uint8)
    _, large_buf = cv2.imencode(".jpg", large_img)
    opt_bytes, opt_mime, ocr_img, orig_dims, opt_dims = validate_and_optimize_image(
        large_buf.tobytes(), max_dim=1600, jpeg_quality=85
    )

    assert opt_mime == "image/jpeg"
    assert orig_dims == (3200, 2400)
    assert opt_dims == (1600, 1200)
    assert max(opt_dims) <= 1600
    assert isinstance(ocr_img, np.ndarray)
    assert len(ocr_img.shape) == 2
    assert len(opt_bytes) > 0


def test_reader_lazy_loading():
    with patch("easyocr.Reader") as mock_reader_cls:
        mock_instance = MagicMock()
        mock_reader_cls.return_value = mock_instance

        import shelfguard.ocr_engine as engine_mod
        engine_mod._EASYOCR_READER = None

        reader1 = _get_easyocr_reader()
        reader2 = _get_easyocr_reader()

        assert reader1 == reader2
        assert mock_reader_cls.call_count == 1


def test_paddleocr_successful_extraction():
    with patch("shelfguard.ocr_engine._get_paddle_reader") as mock_paddle_fn:
        mock_paddle = MagicMock()
        # PaddleOCR return format: [[ [box, (text, conf)], ... ]]
        mock_paddle.ocr.return_value = [[
            ([[0, 0], [100, 0], [100, 20], [0, 20]], ("AMUL BUTTER 500G", 0.98)),
            ([[0, 25], [100, 25], [100, 45], [0, 45]], ("BATCH NO: AB-5501", 0.95)),
            ([[0, 50], [100, 50], [100, 70], [0, 70]], ("PKD: 10/08/2026", 0.94)),
            ([[0, 75], [100, 75], [100, 95], [0, 95]], ("USE BY: 10/02/2027", 0.96)),
            ([[0, 100], [100, 100], [100, 120], [0, 120]], ("MRP RS. 275.00", 0.97)),
        ]]
        mock_paddle_fn.return_value = mock_paddle

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)

        result = extract_product_data(buf.tobytes())

        assert result.success is True
        assert result.ocr_engine == "paddleocr"
        assert result.fallback_used is False
        assert result.product_name == "AMUL BUTTER 500G"
        assert result.batch_number == "AB-5501"
        assert result.manufacturing_date == "2026-08-10"
        assert result.expiry_date == "2027-02-10"
        assert result.mrp == 275.0
        assert result.base_price == 275.0
        assert result.category == "Dairy"
        assert result.manufacturer == "Amul (GCMMF)"
        assert result.fields["product_name"] == "AMUL BUTTER 500G"
        assert result.fields["expiry_date"] == "2027-02-10"


def test_paddleocr_failure_fallback_to_easyocr():
    with patch("shelfguard.ocr_engine._get_paddle_reader") as mock_paddle_fn, \
         patch("shelfguard.ocr_engine._extract_raw_easyocr") as mock_easyocr_fn:

        mock_paddle_fn.return_value = None  # PaddleOCR unavailable
        mock_easyocr_fn.return_value = {
            "raw_text": "BRITANNIA BREAD\nEXP: 2027-01-15\nMRP: 40.00",
            "lines": ["BRITANNIA BREAD", "EXP: 2027-01-15", "MRP: 40.00"],
            "confidences": [0.92, 0.95, 0.90],
            "avg_confidence": 0.92,
            "engine": "easyocr"
        }

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)

        result = extract_product_data(buf.tobytes())

        assert result.ocr_engine == "easyocr"
        assert result.product_name == "BRITANNIA BREAD"
        assert result.expiry_date == "2027-01-15"
        assert result.mrp == 40.0


def test_missing_expiry_date_handling():
    with patch("shelfguard.ocr_engine._extract_raw_ocr") as mock_ocr, \
         patch("shelfguard.ocr_engine._find_gemini_api_key", return_value=None):

        mock_ocr.return_value = {
            "raw_text": "FRESH TOMATOES\nNET WT 1KG\nMRP RS. 60",
            "lines": ["FRESH TOMATOES", "NET WT 1KG", "MRP RS. 60"],
            "confidences": [0.9, 0.8, 0.9],
            "avg_confidence": 0.87,
            "engine": "paddleocr"
        }

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)

        result = extract_product_data(buf.tobytes())

        assert result.expiry_date is None
        assert any(
            "Expiry date could not be confidently identified" in w
            for w in result.warnings
        )


def test_common_indian_date_formats():
    # Test DD/MM/YYYY
    res1 = _extract_structured_fields(
        ["MILK", "EXP: 25/12/2026"], "MILK\nEXP: 25/12/2026"
    )
    assert res1["expiry_date"]["value"] == "2026-12-25"

    # Test DD-MM-YYYY
    res2 = _extract_structured_fields(
        ["CURD", "USE BY: 15-09-2026"], "CURD\nUSE BY: 15-09-2026"
    )
    assert res2["expiry_date"]["value"] == "2026-09-15"

    # Test DD.MM.YYYY
    res3 = _extract_structured_fields(
        ["CHEESE", "BEST BEFORE: 30.11.2026"], "CHEESE\nBEST BEFORE: 30.11.2026"
    )
    assert res3["expiry_date"]["value"] == "2026-11-30"

    # Test YYYY-MM-DD
    res4 = _extract_structured_fields(
        ["PANEER", "EXP DATE: 2026-10-05"], "PANEER\nEXP DATE: 2026-10-05"
    )
    assert res4["expiry_date"]["value"] == "2026-10-05"

    # Test DD/MM/YY
    res5 = _extract_structured_fields(
        ["YOGURT", "EXP: 20/07/26"], "YOGURT\nEXP: 20/07/26"
    )
    assert res5["expiry_date"]["value"] == "2026-07-20"


@patch("shelfguard.ocr_engine.extract_semantic_data")
@patch("shelfguard.ocr_engine._extract_raw_ocr")
@patch("shelfguard.ocr_engine._find_gemini_api_key", return_value="fake-api-key")
def test_gemini_fallback_trigger_on_low_confidence(mock_key, mock_ocr, mock_semantic):
    # OCR has ambiguous/missing expiry
    mock_ocr.return_value = {
        "raw_text": "UNREADABLE STAMP\nSOME PRODUCT\nMRP 90",
        "lines": ["UNREADABLE STAMP", "SOME PRODUCT", "MRP 90"],
        "confidences": [0.4, 0.4, 0.5],
        "avg_confidence": 0.43,
        "engine": "paddleocr"
    }

    mock_semantic.return_value = {
        "product_name": {"value": "ORGANIC HONEY", "confidence": 0.95, "source": "gemini"},
        "manufacturer": {"value": "Dabur India", "confidence": 0.90, "source": "gemini"},
        "batch_number": {"value": "DH-102", "confidence": 0.88, "source": "gemini"},
        "manufacturing_date": {"value": "2026-01-01", "confidence": 0.90, "source": "gemini"},
        "expiry_date": {"value": "2027-12-31", "confidence": 0.96, "source": "gemini"},
        "mrp": {"value": 90.0, "confidence": 0.90, "source": "gemini"},
        "base_price": {"value": 90.0, "confidence": 0.90, "source": "gemini"},
        "category": {"value": "Packaged Foods", "confidence": 0.90, "source": "gemini"},
        "warnings": [],
        "conflicts": []
    }

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)

    result = extract_product_data(buf.tobytes())

    assert result.fallback_used is True
    assert result.semantic_engine == "gemini"
    assert result.product_name == "ORGANIC HONEY"
    assert result.expiry_date == "2027-12-31"


@patch("shelfguard.ocr_engine.extract_semantic_data")
@patch("shelfguard.ocr_engine._extract_raw_ocr")
@patch("shelfguard.ocr_engine._find_gemini_api_key", return_value="fake-api-key")
def test_gemini_503_and_rate_limit_response(mock_key, mock_ocr, mock_semantic):
    mock_ocr.return_value = {
        "raw_text": "AMUL BUTTER\nBATCH NO: AB-900\nMRP RS. 105",
        "lines": ["AMUL BUTTER", "BATCH NO: AB-900", "MRP RS. 105"],
        "confidences": [0.88, 0.85, 0.90],
        "avg_confidence": 0.88,
        "engine": "paddleocr"
    }

    # Gemini returns 503 rate limit
    mock_semantic.side_effect = SemanticRateLimitError("Semantic extraction service is busy (503).")

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)

    result = extract_product_data(buf.tobytes())

    assert result.success is True
    assert result.product_name == "AMUL BUTTER"
    assert result.batch_number == "AB-900"
    assert result.mrp == 105.0
    assert any("Gemini AI fallback unavailable" in w for w in result.warnings)


@patch("shelfguard.ocr_engine.extract_semantic_data")
@patch("shelfguard.ocr_engine._extract_raw_ocr")
@patch("shelfguard.ocr_engine._find_gemini_api_key", return_value="fake-api-key")
def test_gemini_timeout_handling(mock_key, mock_ocr, mock_semantic):
    mock_ocr.return_value = {
        "raw_text": "HERITAGE MILK\nBATCH: HM-01",
        "lines": ["HERITAGE MILK", "BATCH: HM-01"],
        "confidences": [0.8, 0.8],
        "avg_confidence": 0.8,
        "engine": "paddleocr"
    }

    mock_semantic.side_effect = SemanticExtractionError(
        "Network timeout communicating with Gemini."
    )

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)

    result = extract_product_data(buf.tobytes())

    assert result.success is True
    assert result.product_name == "HERITAGE MILK"
    assert any("fallback unavailable" in w for w in result.warnings)


def test_missing_gemini_api_key():
    with patch("shelfguard.ocr_engine._find_gemini_api_key", return_value=None), \
         patch("shelfguard.ocr_engine._extract_raw_ocr") as mock_ocr:

        mock_ocr.return_value = {
            "raw_text": "PARLE-G BISCUITS\nEXP: 2026-11-20\nMRP RS. 10",
            "lines": ["PARLE-G BISCUITS", "EXP: 2026-11-20", "MRP RS. 10"],
            "confidences": [0.95, 0.95, 0.95],
            "avg_confidence": 0.95,
            "engine": "paddleocr"
        }

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)

        result = extract_product_data(buf.tobytes())

        assert result.fallback_used is False
        assert result.product_name == "PARLE-G BISCUITS"
        assert result.expiry_date == "2026-11-20"


def test_structured_field_extraction_rules():
    lines = [
        "HERITAGE FOODS LTD",
        "MANGO PICKLE 500G",
        "BATCH NO: HP-9092",
        "MFG DATE: 15/01/2026",
        "BEST BEFORE: 15/01/2027",
        "MRP RS. 185.00",
        "SKU: PKL-MNG-500"
    ]
    raw_text = "\n".join(lines)
    fields = _extract_structured_fields(lines, raw_text, engine_source="paddleocr")

    assert fields["product_name"]["value"] == "MANGO PICKLE 500G"
    assert fields["manufacturer"]["value"] == "Heritage Foods Ltd"
    assert fields["batch_number"]["value"] == "HP-9092"
    assert fields["manufacturing_date"]["value"] == "2026-01-15"
    assert fields["expiry_date"]["value"] == "2027-01-15"
    assert fields["mrp"]["value"] == 185.0
    assert fields["category"]["value"] == "Pickles"
    assert fields["sku"]["value"] == "PKL-MNG-500"


def test_ocr_scan_response_schema_structure():
    with patch("shelfguard.ocr_engine._extract_raw_ocr") as mock_ocr:
        mock_ocr.return_value = {
            "raw_text": "AMUL TAZA MILK\nEXP: 2026-09-10\nMRP 32",
            "lines": ["AMUL TAZA MILK", "EXP: 2026-09-10", "MRP 32"],
            "confidences": [0.95, 0.95, 0.95],
            "avg_confidence": 0.95,
            "engine": "paddleocr"
        }

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)

        result = extract_product_data(buf.tobytes())

        # Verify schema compliance
        assert hasattr(result, "success")
        assert hasattr(result, "ocr_engine")
        assert hasattr(result, "fallback_used")
        assert hasattr(result, "overall_confidence")
        assert hasattr(result, "fields")
        assert hasattr(result, "warnings")
        assert result.fields["product_name"] == "AMUL TAZA MILK"
        assert result.fields["expiry_date"] == "2026-09-10"
        assert result.fields["mrp"] == 32.0
