import concurrent.futures
import importlib
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from shelfguard.schemas import FieldExtraction, OcrExtractionResult
from shelfguard.semantic_extractor import (
    SemanticConfigError,
    SemanticExtractionError,
    SemanticRateLimitError,
    _find_gemini_api_key,
    extract_semantic_data,
)

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Base exception for OCR engine failures."""
    pass


class ImageProcessingError(OCRError):
    """Raised when image decoding or preprocessing fails."""
    pass


# Lazy loaded engine singletons
_PADDLE_OCR_READER: Any = None
_EASYOCR_READER: Any = None


def _get_paddle_reader() -> Any:
    """
    Lazy loads and initializes the PaddleOCR PP-OCRv4 Mobile engine.
    Returns None if PaddleOCR is not installed or initialization fails.
    """
    global _PADDLE_OCR_READER
    if _PADDLE_OCR_READER is None:
        try:
            logger.info("[Scanner] Initializing PaddleOCR reader (PP-OCRv4 Mobile, CPU)...")
            paddle_module = importlib.import_module("paddleocr")
            PaddleOCR = getattr(paddle_module, "PaddleOCR")
            _PADDLE_OCR_READER = PaddleOCR(
                use_angle_cls=True,
                lang='en',
                use_gpu=False,
                show_log=False
            )
            logger.info("[Scanner] PaddleOCR reader initialized successfully.")
        except Exception as e:
            logger.info(f"[Scanner] PaddleOCR not available ({e}). Using EasyOCR fallback.")
            return None
    return _PADDLE_OCR_READER


def _get_easyocr_reader() -> Any:
    """
    Lazy loads and initializes EasyOCR as a secondary fallback engine.
    """
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        logger.info("[Scanner] Initializing EasyOCR reader (en, GPU=False)...")
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False)
            logger.info("[Scanner] EasyOCR reader initialized successfully.")
        except Exception as e:
            logger.error(f"[Scanner] Failed to initialize EasyOCR: {e}", exc_info=True)
            raise OCRError(f"Failed to initialize EasyOCR engine: {e}") from e
    return _EASYOCR_READER


def _get_reader() -> Any:
    """Backwards-compatible getter for EasyOCR reader singleton in legacy tests."""
    return _get_easyocr_reader()


def validate_and_optimize_image(
    image_bytes: bytes,
    max_dim: int = 1600,
    jpeg_quality: int = 85
) -> Tuple[bytes, str, np.ndarray, Tuple[int, int], Tuple[int, int]]:
    """
    Validates, resizes (preserving aspect ratio up to max_dim), and compresses image.
    Generates:
      1. optimized_bytes: Compressed JPEG bytes for Vision API / storage
      2. mime_type: 'image/jpeg'
      3. ocr_img: Grayscale + mild contrast enhanced ndarray for OCR
      4. orig_dims: (width, height)
      5. opt_dims: (width, height)
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

        orig_h, orig_w = img.shape[:2]

        # Resize if image exceeds maximum allowed dimension
        if max(orig_h, orig_w) > max_dim:
            scale = max_dim / float(max(orig_h, orig_w))
            new_w, new_h = max(1, int(orig_w * scale)), max(1, int(orig_h * scale))
            resized_color = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            resized_color = img
            new_w, new_h = orig_w, orig_h

        # Re-encode optimized image to JPEG
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
        success, enc_buf = cv2.imencode(".jpg", resized_color, encode_param)
        if success:
            optimized_bytes = enc_buf.tobytes()
        else:
            optimized_bytes = image_bytes

        # Generate grayscale + contrast-enhanced image for OCR
        gray = cv2.cvtColor(resized_color, cv2.COLOR_BGR2GRAY)
        ocr_img = cv2.convertScaleAbs(gray, alpha=1.15, beta=10)

        logger.info(
            f"[Scanner] Original image: {orig_w}x{orig_h} ({len(image_bytes)/1024:.1f} KB) -> "
            f"Optimized: {new_w}x{new_h} ({len(optimized_bytes)/1024:.1f} KB)"
        )

        return optimized_bytes, "image/jpeg", ocr_img, (orig_w, orig_h), (new_w, new_h)

    except ImageProcessingError:
        raise
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}", exc_info=True)
        raise ImageProcessingError(f"Unable to read the uploaded image: {str(e)}") from e


def _preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Backwards-compatible wrapper returning the preprocessed OCR image array."""
    _, _, ocr_img, _, _ = validate_and_optimize_image(image_bytes)
    return ocr_img


def _extract_raw_paddle_ocr(
    ocr_img: np.ndarray,
    timeout_seconds: float = 15.0
) -> Optional[Dict[str, Any]]:
    """
    Runs text extraction using PaddleOCR PP-OCRv4 Mobile engine.
    """
    reader = _get_paddle_reader()
    if reader is None:
        return None

    def run_paddle():
        if len(ocr_img.shape) == 2:
            color_img = cv2.cvtColor(ocr_img, cv2.COLOR_GRAY2BGR)
        else:
            color_img = ocr_img
        return reader.ocr(color_img, cls=True)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_paddle)
            results = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        logger.warning(f"[Scanner] PaddleOCR timed out after {timeout_seconds}s.")
        return None
    except Exception as e:
        logger.warning(f"[Scanner] PaddleOCR execution failed ({e}).")
        return None

    if not results or not results[0]:
        return {
            "raw_text": "",
            "lines": [],
            "confidences": [],
            "avg_confidence": 0.0,
            "engine": "paddleocr"
        }

    lines: List[str] = []
    confs: List[float] = []

    for page in results:
        if not page:
            continue
        for item in page:
            if len(item) >= 2 and len(item[1]) >= 2:
                text = str(item[1][0]).strip()
                score = float(item[1][1])
                if text:
                    lines.append(text)
                    confs.append(score)

    full_text = "\n".join(lines)
    avg_conf = sum(confs) / float(len(confs)) if confs else 0.0

    return {
        "raw_text": full_text,
        "lines": lines,
        "confidences": confs,
        "avg_confidence": avg_conf,
        "engine": "paddleocr"
    }


def _extract_raw_easyocr(ocr_img: np.ndarray, timeout_seconds: float = 15.0) -> Dict[str, Any]:
    """
    Runs text extraction using EasyOCR engine with strict timeout.
    """
    reader = _get_easyocr_reader()

    def run_readtext():
        return reader.readtext(ocr_img)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_readtext)
            results = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        logger.warning(f"[Scanner] EasyOCR timed out after {timeout_seconds}s.")
        return {
            "raw_text": "",
            "lines": [],
            "confidences": [],
            "avg_confidence": 0.0,
            "timed_out": True,
            "engine": "easyocr"
        }
    except Exception as e:
        logger.error(f"EasyOCR readtext failed: {e}", exc_info=True)
        raise OCRError(f"OCR text extraction failed: {str(e)}") from e

    if not results:
        return {
            "raw_text": "",
            "lines": [],
            "confidences": [],
            "avg_confidence": 0.0,
            "engine": "easyocr"
        }

    lines = [item[1] for item in results]
    confs = [float(item[2]) for item in results]
    full_text = "\n".join(lines)
    avg_conf = sum(confs) / float(len(confs)) if confs else 0.0

    return {
        "raw_text": full_text,
        "lines": lines,
        "confidences": confs,
        "avg_confidence": avg_conf,
        "engine": "easyocr"
    }


def _extract_raw_ocr(
    image_input: Union[bytes, np.ndarray],
    timeout_seconds: float = 15.0
) -> Dict[str, Any]:
    """
    Primary OCR router: Tries PaddleOCR first, falling back to EasyOCR if unavailable.
    """
    if isinstance(image_input, (bytes, bytearray)):
        processed_img = _preprocess_image(image_input)
    else:
        processed_img = image_input

    # 1. Primary engine: Local PaddleOCR
    paddle_res = _extract_raw_paddle_ocr(processed_img, timeout_seconds=timeout_seconds)
    if paddle_res is not None and len(paddle_res.get("lines", [])) > 0:
        return paddle_res

    # 2. Secondary fallback: EasyOCR
    easy_res = _extract_raw_easyocr(processed_img, timeout_seconds=timeout_seconds)
    return easy_res


def _extract_structured_fields(
    lines: List[str],
    raw_text: str,
    engine_source: str = "paddleocr"
) -> Dict[str, Any]:
    """
    Extracts structured product fields from raw OCR text candidates.
    Supports comprehensive Indian packaging conventions.
    """
    mfg_date = None
    mfg_conf = 0.0
    exp_date = None
    exp_conf = 0.0
    mrp = None
    mrp_conf = 0.0
    batch = None
    batch_conf = 0.0
    prod_name = None
    prod_name_conf = 0.0
    manufacturer = None
    mfr_conf = 0.0
    category = None
    cat_conf = 0.0
    sku = None
    sku_conf = 0.0

    mfg_keywords = ['MFG', 'MFD', 'PKD', 'PACKED', 'PROD', 'DATE OF MFG', 'MANUFACTURED']
    exp_keywords = ['EXP', 'EXPIRY', 'USE BY', 'BEST BEFORE', 'BB', 'USE BEFORE', 'EXP DATE']
    mfr_keywords = ['MFD BY', 'MANUFACTURED BY', 'PACKED BY', 'MKTD BY', 'PRODUCED BY', 'MFG BY']

    known_brands = [
        ('AMUL', 'Amul (GCMMF)', 'Dairy'),
        ('BRITANNIA', 'Britannia Industries', 'Bakery'),
        ('HERITAGE FOODS', 'Heritage Foods Ltd', 'Dairy'),
        ('HERITAGE', 'Heritage Foods Ltd', 'Dairy'),
        ('NESTLE', 'Nestle India', 'Packaged Foods'),
        ('DABUR', 'Dabur India', 'Packaged Foods'),
        ('PARLE', 'Parle Products', 'Bakery'),
        ('HALDIRAM', "Haldiram's", 'Snacks'),
        ('MOTHER DAIRY', 'Mother Dairy', 'Dairy'),
        ('NANDINI', 'KMF Nandini', 'Dairy'),
        ('TATAPRODUCTS', 'Tata Consumer Products', 'Beverages'),
        ('TATA', 'Tata Consumer Products', 'Beverages'),
        ('EVEREST', 'Everest Spices', 'Spices'),
        ('MDH', 'MDH Spices', 'Spices'),
        ('KRAFT', 'Kraft Foods', 'Packaged Foods'),
        ('CADBURY', 'Cadbury (Mondelez)', 'Confectionery'),
    ]

    category_keywords = [
        ('Dairy', ['MILK', 'BUTTER', 'CHEESE', 'PANEER', 'CURD', 'YOGURT', 'GHEE', 'TAZA']),
        ('Bakery', ['BREAD', 'CAKE', 'BUN', 'BISCUIT', 'COOKIE', 'CROISSANT', 'RUSK', 'TOAST']),
        ('Beverages', ['JUICE', 'TEA', 'COFFEE', 'DRINK', 'SODA', 'WATER', 'SHAKE', 'COLA']),
        ('Pickles', ['PICKLE', 'ACHAR', 'CHUTNEY', 'MANGO PICKLE', 'LIME PICKLE']),
        ('Snacks', ['CHIPS', 'NAMKEEN', 'CRISPS', 'POPCORN', 'SNACK', 'BHUJIA', 'MIXTURE']),
        ('Produce', ['TOMATO', 'APPLE', 'BANANA', 'VEGETABLE', 'FRUIT', 'ONION', 'POTATO']),
        ('Grains', ['RICE', 'WHEAT', 'FLOUR', 'ATTA', 'DAL', 'PULSE', 'CEREAL', 'OATS']),
        ('Packaged Foods', ['SAUCE', 'KETCHUP', 'PASTA', 'NOODLE', 'JAM', 'SPREAD', 'MAYONNAISE']),
    ]

    def parse_date_string(raw_str: str) -> Optional[str]:
        d_patterns = [
            r'\b(20\d{2})[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])\b',
            r'\b(0?[1-9]|[12]\d|3[01])[-/\.](0?[1-9]|1[0-2])[-/\.](20\d{2})\b',
            r'\b(0?[1-9]|[12]\d|3[01])[-/\.](0?[1-9]|1[0-2])[-/\.](\d{2})\b',
            r'\b(0?[1-9]|1[0-2])[-/\.](20\d{2})\b'
        ]
        for pat in d_patterns:
            m = re.search(pat, raw_str)
            if m:
                raw_d = m.group(0)
                for fmt in (
                    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d/%m/%Y",
                    "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%m/%Y", "%m-%Y"
                ):
                    try:
                        dt = datetime.strptime(raw_d, fmt)
                        if dt.year < 2000:
                            dt = dt.replace(year=dt.year + 100)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
        return None

    for line in lines:
        upper = line.upper().strip()

        # 1. Date extraction
        norm_d = parse_date_string(upper)
        if norm_d:
            if any(k in upper for k in mfg_keywords) and not mfg_date:
                mfg_date = norm_d
                mfg_conf = 0.90
            elif any(k in upper for k in exp_keywords) and not exp_date:
                exp_date = norm_d
                exp_conf = 0.95
            elif not exp_date and not any(k in upper for k in mfg_keywords):
                exp_date = norm_d
                exp_conf = 0.70

        # 2. MRP extraction
        mrp_m = re.search(r'(?:MRP|RS\.?|₹|PRICE|M\.R\.P)\s*[:\.\-]?\s*(\d+(?:\.\d{1,2})?)', upper)
        if mrp_m and not mrp:
            try:
                mrp = float(mrp_m.group(1))
                mrp_conf = 0.90
            except ValueError:
                pass

        # 3. Batch extraction
        b_pat = (
            r'\b(?:BATCH(?:\s+NO)?|LOT(?:\s+NUMBER|\s*#)?|B\.NO|BNO|LOT)'
            r'\s*[:\.\-]?\s*([A-Z0-9\-_/]{2,25})\b'
        )
        b_m = re.search(b_pat, upper)
        if b_m and not batch:
            batch = b_m.group(1).strip()
            batch_conf = 0.88

        # 4. Manufacturer extraction
        for kw in mfr_keywords:
            if kw in upper and not manufacturer:
                after_kw = upper.split(kw, 1)[1].strip(" :.-")
                if len(after_kw) >= 3:
                    manufacturer = after_kw.title()
                    mfr_conf = 0.85
                    break

        brand_default_cat = None
        for brand_key, brand_full, brand_cat in known_brands:
            if brand_key in upper:
                if not manufacturer:
                    manufacturer = brand_full
                    mfr_conf = 0.90
                if brand_cat:
                    brand_default_cat = brand_cat

        # 5. SKU extraction
        sku_m = re.search(r'\b(?:SKU|ITEM\s+CODE|CODE)\s*[:\.\-]?\s*([A-Z0-9\-_]{3,20})\b', upper)
        if sku_m and not sku:
            sku = sku_m.group(1).strip()
            sku_conf = 0.85

        # 6. Category extraction (specific product keyword takes precedence)
        for cat_name, cat_kws in category_keywords:
            if any(kw in upper for kw in cat_kws):
                category = cat_name
                cat_conf = 0.90
                break

        if not category and brand_default_cat:
            category = brand_default_cat
            cat_conf = 0.80

        # 7. Product name heuristic
        stop_words = mfg_keywords + exp_keywords + mfr_keywords + [
            'MRP', 'PRICE', 'BATCH', 'NET WT', 'WEIGHT', 'GRAMS', 'QTY', 'LOT',
            'INCL', 'TAXES', 'REFRIGERATED', 'KEEP', 'LTD', 'LIMITED', 'PVT',
            'CORP', 'INDUSTRIES', 'FOODS', 'PRIVATE', 'COMPANY', 'SKU', 'ITEM CODE'
        ]
        is_company = any(k in upper for k in ['LTD', 'LIMITED', 'PVT', 'INDUSTRIES', 'CORP'])
        if not prod_name and len(line.strip()) >= 3 and not is_company:
            if not any(k in upper for k in stop_words) and not re.search(r'^\d+[\s\w]*$', upper):
                prod_name = line.strip()
                prod_name_conf = 0.75

    base_price = mrp
    base_price_conf = mrp_conf

    return {
        "product_name": {
            "value": prod_name, "confidence": prod_name_conf, "source": engine_source
        },
        "sku": {"value": sku, "confidence": sku_conf, "source": engine_source},
        "manufacturer": {
            "value": manufacturer, "confidence": mfr_conf, "source": engine_source
        },
        "batch_number": {"value": batch, "confidence": batch_conf, "source": engine_source},
        "manufacturing_date": {
            "value": mfg_date, "confidence": mfg_conf, "source": engine_source
        },
        "expiry_date": {"value": exp_date, "confidence": exp_conf, "source": engine_source},
        "mrp": {"value": mrp, "confidence": mrp_conf, "source": engine_source},
        "base_price": {
            "value": base_price, "confidence": base_price_conf, "source": engine_source
        },
        "category": {"value": category, "confidence": cat_conf, "source": engine_source},
        "warnings": [],
        "conflicts": []
    }


def _fallback_heuristic_extraction(lines: List[str], raw_text: str) -> Dict[str, Any]:
    """Backwards-compatible wrapper for heuristic extraction."""
    return _extract_structured_fields(lines, raw_text, engine_source="ocr_heuristic")


def extract_product_data(
    image_bytes: bytes,
    mime_type: str = "image/jpeg"
) -> OcrExtractionResult:
    """
    Optimized Primary PaddleOCR + Fallback Gemini Vision Pipeline.
    """
    t_start = time.time()
    logger.info(f"[Scanner] Image received ({len(image_bytes)/1024:.1f} KB, type: {mime_type})")

    if not image_bytes:
        raise ImageProcessingError("No image was provided.")

    # 1. Preprocessing & Size Optimization
    t_prep_start = time.time()
    optimized_bytes, opt_mime, ocr_img, orig_dims, opt_dims = validate_and_optimize_image(
        image_bytes
    )
    t_prep_end = time.time()
    logger.info(
        f"[Scanner] Image preprocessing: {(t_prep_end - t_prep_start)*1000:.1f} ms "
        f"(Original: {orig_dims[0]}x{orig_dims[1]}, Optimized: {opt_dims[0]}x{opt_dims[1]})"
    )

    # 2. Local OCR Extraction
    t_ocr_start = time.time()
    ocr_data = _extract_raw_ocr(ocr_img)
    raw_ocr_lines = ocr_data.get("lines", [])
    raw_text = ocr_data.get("raw_text", "")
    ocr_engine_name = ocr_data.get("engine", "paddleocr")
    t_ocr_end = time.time()
    logger.info(
        f"[Scanner] {ocr_engine_name.upper()}: {(t_ocr_end - t_ocr_start)*1000:.1f} ms "
        f"(Found {len(raw_ocr_lines)} text lines)"
    )

    # 3. Local Structured Field Extraction
    t_parse_start = time.time()
    structured_data = _extract_structured_fields(
        raw_ocr_lines, raw_text, engine_source=ocr_engine_name
    )

    # Determine if fallback is needed
    exp_extracted = structured_data["expiry_date"]["value"] is not None
    exp_conf = structured_data["expiry_date"]["confidence"]
    prod_extracted = structured_data["product_name"]["value"] is not None
    prod_conf = structured_data["product_name"]["confidence"]

    gemini_key = _find_gemini_api_key()
    needs_fallback = (not exp_extracted or exp_conf < 0.6 or not prod_extracted or prod_conf < 0.5)

    fallback_used = False
    semantic_engine = None

    # 4. Optional Gemini Vision Fallback
    if needs_fallback and gemini_key:
        t_ai_start = time.time()
        logger.info("[Scanner] Local extraction incomplete; invoking Gemini Vision fallback...")
        try:
            gemini_data = extract_semantic_data(
                image_bytes=optimized_bytes,
                raw_ocr_lines=raw_ocr_lines,
                mime_type=opt_mime,
                max_retries=2
            )
            field_keys = [
                "product_name", "manufacturer", "batch_number", "manufacturing_date",
                "expiry_date", "mrp", "base_price", "category", "sku"
            ]
            for k in field_keys:
                g_item = gemini_data.get(k)
                if g_item and g_item.get("value") is not None:
                    structured_data[k] = g_item

            if "warnings" in gemini_data:
                structured_data["warnings"].extend(gemini_data["warnings"])
            if "conflicts" in gemini_data:
                structured_data["conflicts"].extend(gemini_data["conflicts"])

            fallback_used = True
            semantic_engine = "gemini"
            t_ai_end = time.time()
            logger.info(
                f"[Scanner] Gemini Fallback: {(t_ai_end - t_ai_start)*1000:.1f} ms (SUCCESS)"
            )

        except SemanticConfigError as e:
            logger.warning(f"[Scanner] Gemini not configured: {e}")
        except (SemanticRateLimitError, SemanticExtractionError) as e:
            logger.warning(f"[Scanner] Gemini fallback unavailable ({e}). Using local OCR output.")
            structured_data["warnings"].append(
                "Gemini AI fallback unavailable (busy). Output extracted using local OCR."
            )
        except Exception as e:
            logger.error(f"[Scanner] Gemini fallback error: {e}", exc_info=True)

    # 5. Assemble structured result
    result = OcrExtractionResult()
    result.success = True
    result.ocr_engine = ocr_engine_name
    result.fallback_used = fallback_used
    result.semantic_engine = semantic_engine
    result.raw_text = raw_text
    result.warnings = list(structured_data.get("warnings", []))
    result.conflicts = list(structured_data.get("conflicts", []))

    conf_values = []
    all_fields = [
        "product_name", "manufacturer", "sku", "batch_number",
        "manufacturing_date", "expiry_date", "mrp", "base_price", "category"
    ]
    for field_key in all_fields:
        field_info = structured_data.get(field_key) or {}
        val = field_info.get("value")
        conf = float(field_info.get("confidence", 0.0))
        src = field_info.get("source", ocr_engine_name)

        setattr(result, field_key, val)
        result.confidence[field_key] = round(conf, 2)
        result.semantic_fields[field_key] = FieldExtraction(
            value=val,
            confidence=round(conf, 2),
            source=str(src or ocr_engine_name)
        )
        result.fields[field_key] = val
        if conf > 0:
            conf_values.append(conf)

    if conf_values:
        result.overall_confidence = round(sum(conf_values) / len(conf_values), 2)
    else:
        result.overall_confidence = round(ocr_data.get("avg_confidence", 0.0), 2)

    # If base_price wasn't set, default from MRP
    if result.mrp and not result.base_price:
        result.base_price = result.mrp
        result.confidence["base_price"] = result.confidence.get("mrp", 0.8)
        result.fields["base_price"] = result.mrp

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

    t_parse_end = time.time()
    logger.info(f"[Scanner] Parsing: {(t_parse_end - t_parse_start)*1000:.1f} ms")

    t_total = time.time() - t_start
    logger.info(
        f"[Scanner] Total: {t_total*1000:.1f} ms "
        f"(Engine: {ocr_engine_name}, Fallback: {fallback_used})"
    )

    return result
