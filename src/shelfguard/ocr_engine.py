import logging
import re
from datetime import datetime
from typing import Any, Dict, List

import cv2
import numpy as np

from shelfguard.schemas import FieldExtraction, OcrExtractionResult
from shelfguard.semantic_extractor import (
    SemanticConfigError,
    SemanticExtractionError,
    SemanticRateLimitError,
    extract_semantic_data,
)

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Base exception for OCR engine failures."""
    pass


class ImageProcessingError(OCRError):
    """Raised when image decoding or preprocessing fails."""
    pass


# Lazy loaded EasyOCR reader singleton
_EASYOCR_READER: Any = None


def _get_reader() -> Any:
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        logger.info("Initializing EasyOCR reader (en, GPU=False)...")
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False)
            logger.info("EasyOCR reader initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}", exc_info=True)
            raise OCRError(f"Failed to initialize EasyOCR engine: {e}") from e
    return _EASYOCR_READER


def _preprocess_image(image_bytes: bytes) -> np.ndarray:
    """
    Safely decode and preprocess image bytes using OpenCV.
    Converts to grayscale and applies mild contrast enhancement without destructive thresholding.
    """
    if not image_bytes or len(image_bytes) == 0:
        raise ImageProcessingError("No image was provided or image bytes are empty.")

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ImageProcessingError(
                "Unable to read the uploaded image. Corrupt or unsupported format."
            )

        # Resize if image is excessively large
        max_dim = 1600
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Grayscale conversion
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Mild contrast enhancement
        enhanced = cv2.convertScaleAbs(gray, alpha=1.15, beta=10)

        return enhanced
    except ImageProcessingError:
        raise
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}", exc_info=True)
        raise ImageProcessingError(f"Unable to read the uploaded image: {str(e)}") from e


def _extract_raw_ocr(image_bytes: bytes) -> Dict[str, Any]:
    """Extracts raw text candidates and bounding confidence using EasyOCR."""
    processed_img = _preprocess_image(image_bytes)
    reader = _get_reader()
    
    try:
        results = reader.readtext(processed_img)
    except Exception as e:
        logger.error(f"EasyOCR readtext failed: {e}", exc_info=True)
        raise OCRError(f"OCR text extraction failed: {str(e)}") from e

    if not results:
        logger.info("EasyOCR found no text in image.")
        return {
            "raw_text": "",
            "lines": [],
            "confidences": [],
            "avg_confidence": 0.0
        }

    lines = [item[1] for item in results]
    confs = [float(item[2]) for item in results]
    full_text = "\n".join(lines)
    avg_conf = sum(confs) / float(len(confs)) if confs else 0.0

    return {
        "raw_text": full_text,
        "lines": lines,
        "confidences": confs,
        "avg_confidence": avg_conf
    }


def _fallback_heuristic_extraction(lines: List[str], raw_text: str) -> Dict[str, Any]:
    """
    Lightweight heuristic fallback used only if semantic AI is completely unconfigured.
    """
    mfg_date = None
    exp_date = None
    mrp = None
    batch = None
    prod_name = None

    # Lightweight regex support
    mfg_keywords = ['MFG', 'MFD', 'PKD', 'PACKED']
    exp_keywords = ['EXP', 'EXPIRY', 'USE BY', 'BEST BEFORE']

    for line in lines:
        upper = line.upper()
        # Dates
        d1 = r'\b(20\d{2})[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])\b'
        d2 = r'\b(0?[1-9]|[12]\d|3[01])[-/\.](0?[1-9]|1[0-2])[-/\.](20\d{2}|\d{2})\b'
        d_match = re.search(d1, upper) or re.search(d2, upper)

        if d_match:
            raw_d = d_match.group(0)
            norm_d = raw_d
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%Y"):
                try:
                    dt = datetime.strptime(raw_d, fmt)
                    norm_d = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass

            if any(k in upper for k in mfg_keywords) and not mfg_date:
                mfg_date = norm_d
            elif any(k in upper for k in exp_keywords) and not exp_date:
                exp_date = norm_d

        # MRP
        mrp_m = re.search(r'(?:MRP|RS\.?|₹)\s*[:\.\-]?\s*(\d+(?:\.\d{1,2})?)', upper)
        if mrp_m and not mrp:
            try:
                mrp = float(mrp_m.group(1))
            except ValueError:
                pass

        # Batch
        b_pat = r'\b(?:BATCH(?:\s+NO)?|LOT(?:\s+NUMBER)?|B\.NO)\s*[:\.\-]?\s*([A-Z0-9\-_/]{2,20})\b'
        b_m = re.search(b_pat, upper)
        if b_m and not batch:
            batch = b_m.group(1)

        # Product name heuristic
        stop_words = mfg_keywords + exp_keywords + ['MRP', 'PRICE', 'BATCH', 'NET WT']
        if not prod_name and len(line.strip()) >= 4:
            if not any(k in upper for k in stop_words):
                prod_name = line.strip()

    return {
        "product_name": {"value": prod_name, "confidence": 0.6, "source": "ocr_heuristic"},
        "manufacturer": {"value": None, "confidence": 0.0, "source": "ocr_heuristic"},
        "batch_number": {
            "value": batch, "confidence": 0.6 if batch else 0.0, "source": "ocr_heuristic"
        },
        "manufacturing_date": {
            "value": mfg_date, "confidence": 0.6 if mfg_date else 0.0, "source": "ocr_heuristic"
        },
        "expiry_date": {
            "value": exp_date, "confidence": 0.6 if exp_date else 0.0, "source": "ocr_heuristic"
        },
        "mrp": {"value": mrp, "confidence": 0.6 if mrp else 0.0, "source": "ocr_heuristic"},
        "base_price": {"value": mrp, "confidence": 0.6 if mrp else 0.0, "source": "ocr_heuristic"},
        "category": {"value": None, "confidence": 0.0, "source": "ocr_heuristic"},
        "warnings": [
            "Using offline heuristic extraction because GEMINI_API_KEY is not configured."
        ],
        "conflicts": []
    }


def extract_product_data(image_bytes: bytes, mime_type: str = "image/jpeg") -> OcrExtractionResult:
    """
    Hybrid OCR + Semantic AI Pipeline (Single Image):
    1. OpenCV preprocessing
    2. EasyOCR raw text extraction
    3. Gemini Vision semantic interpretation
    4. Return structured OcrExtractionResult
    """
    if not image_bytes:
        raise ImageProcessingError("No image was provided.")

    # 1 & 2: Preprocessing and EasyOCR
    ocr_data = _extract_raw_ocr(image_bytes)
    raw_ocr_lines = ocr_data["lines"]
    raw_text = ocr_data["raw_text"]

    # 3: Semantic AI Extraction
    try:
        semantic_data = extract_semantic_data(
            image_bytes=image_bytes,
            raw_ocr_lines=raw_ocr_lines,
            mime_type=mime_type
        )
    except SemanticConfigError as config_err:
        logger.warning(f"SemanticConfigError: {config_err}. Falling back to OCR heuristics.")
        semantic_data = _fallback_heuristic_extraction(raw_ocr_lines, raw_text)
    except (SemanticRateLimitError, SemanticExtractionError):
        # Propagate semantic rate-limit / service errors directly so main.py returns clean 503/502
        raise

    # 4: Assemble structured result
    result = OcrExtractionResult()
    result.raw_text = raw_text
    result.warnings = list(semantic_data.get("warnings", []))
    result.conflicts = list(semantic_data.get("conflicts", []))

    def parse_field(field_key: str, target_attr: str):
        field_info = semantic_data.get(field_key) or {}
        val = field_info.get("value")
        conf = float(field_info.get("confidence", 0.0))
        src = field_info.get("source", "semantic")

        setattr(result, target_attr, val)
        result.confidence[target_attr] = round(conf, 2)
        result.semantic_fields[target_attr] = FieldExtraction(
            value=val,
            confidence=round(conf, 2),
            source=src
        )

    parse_field("product_name", "product_name")
    parse_field("manufacturer", "manufacturer")
    parse_field("batch_number", "batch_number")
    parse_field("manufacturing_date", "manufacturing_date")
    parse_field("expiry_date", "expiry_date")
    parse_field("mrp", "mrp")
    parse_field("base_price", "base_price")
    parse_field("category", "category")

    # If base_price wasn't set, default from MRP
    if result.mrp and not result.base_price:
        result.base_price = result.mrp
        result.confidence["base_price"] = result.confidence.get("mrp", 0.8)

    # Expiry validation
    if not result.expiry_date:
        result.warnings.append(
            "Expiry date could not be confidently identified. Please verify or enter manually."
        )

    # Consistency check
    if result.manufacturing_date and result.expiry_date:
        try:
            mfg_dt = datetime.strptime(result.manufacturing_date, "%Y-%m-%d")
            exp_dt = datetime.strptime(result.expiry_date, "%Y-%m-%d")
            if mfg_dt > exp_dt:
                conflict_msg = (
                    f"Manufacturing date ({result.manufacturing_date}) is after "
                    f"Expiry date ({result.expiry_date})."
                )
                if conflict_msg not in result.conflicts:
                    result.conflicts.append(conflict_msg)
        except Exception:
            pass

    return result
