from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from shelfguard.ocr_engine import (
    ImageProcessingError,
    _get_reader,
    _preprocess_image,
    extract_product_data,
)
from shelfguard.semantic_extractor import (
    SemanticConfigError,
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


def test_reader_lazy_loading():
    with patch("easyocr.Reader") as mock_reader_cls:
        mock_instance = MagicMock()
        mock_reader_cls.return_value = mock_instance

        import shelfguard.ocr_engine as engine_mod
        engine_mod._EASYOCR_READER = None

        reader1 = _get_reader()
        reader2 = _get_reader()

        assert reader1 == reader2
        assert mock_reader_cls.call_count == 1


@patch("shelfguard.ocr_engine.extract_semantic_data")
@patch("shelfguard.ocr_engine._extract_raw_ocr")
def test_extract_product_data_hybrid_single_image(mock_ocr, mock_semantic):
    mock_ocr.return_value = {
        "raw_text": "HERITAGE MANGO PICKLE\nEXP: 2027-12-25\nMRP RS. 250",
        "lines": ["HERITAGE MANGO PICKLE", "EXP: 2027-12-25", "MRP RS. 250"],
        "confidences": [0.95, 0.90, 0.88],
        "avg_confidence": 0.91,
    }

    mock_semantic.return_value = {
        "product_name": {"value": "MANGO PICKLE", "confidence": 0.96, "source": "semantic"},
        "manufacturer": {"value": "HERITAGE FOODS", "confidence": 0.90, "source": "semantic"},
        "batch_number": {"value": "HP-501", "confidence": 0.85, "source": "semantic"},
        "manufacturing_date": {"value": "2026-01-10", "confidence": 0.90, "source": "semantic"},
        "expiry_date": {"value": "2027-12-25", "confidence": 0.95, "source": "semantic"},
        "mrp": {"value": 250.0, "confidence": 0.90, "source": "semantic"},
        "base_price": {"value": 250.0, "confidence": 0.90, "source": "semantic"},
        "category": {"value": "Pickles", "confidence": 0.85, "source": "semantic"},
        "warnings": [],
        "conflicts": [],
    }

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)

    result = extract_product_data(buf.tobytes())

    assert result.product_name == "MANGO PICKLE"
    assert result.manufacturer == "HERITAGE FOODS"
    assert result.batch_number == "HP-501"
    assert result.manufacturing_date == "2026-01-10"
    assert result.expiry_date == "2027-12-25"
    assert result.mrp == 250.0
    assert result.category == "Pickles"
    assert result.confidence["expiry_date"] == 0.95


@patch("shelfguard.ocr_engine.extract_semantic_data")
@patch("shelfguard.ocr_engine._extract_raw_ocr")
def test_extract_product_data_config_fallback(mock_ocr, mock_semantic):
    mock_ocr.return_value = {
        "raw_text": "MANGO PICKLE\nEXP: 2027-12-25\nMRP RS. 250\nBATCH NO: B-101",
        "lines": ["MANGO PICKLE", "EXP: 2027-12-25", "MRP RS. 250", "BATCH NO: B-101"],
        "confidences": [0.90, 0.90, 0.90, 0.90],
        "avg_confidence": 0.90,
    }

    mock_semantic.side_effect = SemanticConfigError("GEMINI_API_KEY is not configured.")

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)

    result = extract_product_data(buf.tobytes())

    assert result.expiry_date == "2027-12-25"
    assert result.mrp == 250.0
    assert result.batch_number == "B-101"
    assert len(result.warnings) >= 1
    assert "not configured" in result.warnings[0]
