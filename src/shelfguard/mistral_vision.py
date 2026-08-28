import base64
import calendar
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, Field, field_validator

from shelfguard.config import settings
from shelfguard.schemas import FieldExtraction, OcrExtractionResult

logger = logging.getLogger(__name__)

MISTRAL_API_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"


# Exception Hierarchy
class MistralVisionError(Exception):
    """Base exception for Mistral Vision API errors."""
    pass


class MistralConfigError(MistralVisionError):
    """Raised when MISTRAL_API_KEY is missing or invalid."""
    pass


class MistralRateLimitError(MistralVisionError):
    """Raised when Mistral API returns 429 rate limit."""
    pass


class MistralAPIError(MistralVisionError):
    """Raised when Mistral API returns 4xx/5xx errors."""
    pass


class MistralTimeoutError(MistralVisionError):
    """Raised when Mistral API request times out."""
    pass


class ImageProcessingError(MistralVisionError):
    """Raised when image decoding, format, or resizing fails."""
    pass


# Pydantic Schemas for Raw Model Response Validation
class MistralRawConfidence(BaseModel):
    product_name: Optional[float] = 0.0
    manufacturer: Optional[float] = 0.0
    category: Optional[float] = 0.0
    batch_number: Optional[float] = 0.0
    manufacturing_date: Optional[float] = 0.0
    expiry_date: Optional[float] = 0.0
    mrp: Optional[float] = 0.0
    base_cost_price: Optional[float] = 0.0


class MistralRawExtraction(BaseModel):
    product_name: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    batch_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    mrp: Optional[float] = None
    base_cost_price: Optional[float] = None
    expiry_text: Optional[str] = None
    confidence: Optional[Dict[str, float]] = Field(default_factory=dict)
    warnings: Optional[List[str]] = Field(default_factory=list)

    @field_validator("mrp", "base_cost_price", mode="before")
    @classmethod
    def parse_numeric_price(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v) if v > 0 else None
        if isinstance(v, str):
            # Extract number sequence matching digits and optional decimal point
            match = re.search(r"(\d+(?:\.\d+)?)", v)
            if match:
                try:
                    val = float(match.group(1))
                    return val if val > 0 else None
                except ValueError:
                    return None
            return None
        return None


MISTRAL_VISION_PROMPT = """You are an expert product packaging information extraction system.

Analyze the supplied product packaging image carefully.

Extract ONLY information that is visibly present in the image.

Do not guess or hallucinate missing information.

Pay special attention to:
- product name
- manufacturer/brand
- batch or lot number
- manufacturing date
- expiry date
- MRP
- product category

Look at small printed text, stickers, labels, and date markings carefully.

Indian packaging may use formats such as:
DD/MM/YYYY
DD-MM-YYYY
MM/YYYY
Best Before X months from manufacturing
Use By
Expiry
EXP
MFG
MFD
PKD

If the package says something like:
'Best Before 6 Months From MFD'

and the manufacturing date is clearly visible, calculate the expiry date
ONLY if the relationship is unambiguous.

If a field cannot be confidently determined from the image, return null.

Never invent a value.

Return ONLY valid JSON matching the exact schema below.
Every scalar field must be a scalar. Do not return objects for scalar fields.
manufacturer must be a string or null.
product_name must be a string or null.
category must be a string or null.
batch_number must be a string or null.
manufacturing_date must be a string or null.
expiry_date must be a string or null.
mrp must be a number or null.
base_cost_price must be a number or null.
expiry_text must be a string or null.
confidence values must be numbers between 0 and 1.
warnings must be an array of strings.

Matching schema:
{
  "product_name": null,
  "manufacturer": null,
  "category": null,
  "batch_number": null,
  "manufacturing_date": null,
  "expiry_date": null,
  "mrp": null,
  "base_cost_price": null,
  "expiry_text": null,
  "confidence": {
    "product_name": 0.0,
    "manufacturer": 0.0,
    "category": 0.0,
    "batch_number": 0.0,
    "manufacturing_date": 0.0,
    "expiry_date": 0.0,
    "mrp": 0.0
  },
  "warnings": []
}"""


def _normalize_manufacturer(val: Any) -> Optional[str]:
    """
    Normalizes manufacturer field.
    Handles strings, nested dicts (company > manufacturer > name > brand), and unexpected types.
    """
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, dict):
        priority_keys = [
            "company",
            "manufacturer",
            "name",
            "brand",
            "value",
            "title",
            "label",
            "text",
        ]
        for key in priority_keys:
            if key in val and val[key] is not None:
                res = _normalize_manufacturer(val[key])
                if res:
                    return res
        for sub_v in val.values():
            if isinstance(sub_v, str) and sub_v.strip():
                return sub_v.strip()
        return None
    if isinstance(val, (list, tuple)):
        items = [_normalize_manufacturer(item) for item in val]
        valid_items = [i for i in items if i]
        return ", ".join(valid_items) if valid_items else None
    return None


def _normalize_string_field(val: Any, priority_keys: Optional[List[str]] = None) -> Optional[str]:
    """
    Safely normalizes generic scalar string fields from model response.
    Handles strings, numeric types, nested objects, and arrays.
    """
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return str(val)
    if isinstance(val, dict):
        keys = priority_keys or ["value", "name", "title", "text", "date", "number", "code"]
        for key in keys:
            if key in val and val[key] is not None:
                res = _normalize_string_field(val[key], keys)
                if res:
                    return res
        for sub_v in val.values():
            if isinstance(sub_v, str) and sub_v.strip():
                return sub_v.strip()
        return None
    if isinstance(val, (list, tuple)):
        for item in val:
            res = _normalize_string_field(item, priority_keys)
            if res:
                return res
        return None
    return None


def _normalize_numeric_price(val: Any) -> Optional[float]:
    """
    Extracts numeric float price from floats, ints, currency strings, or nested objects.
    """
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val) if val > 0 else None
    if isinstance(val, str):
        match = re.search(r"(\d+(?:\.\d+)?)", val)
        if match:
            try:
                num = float(match.group(1))
                return num if num > 0 else None
            except ValueError:
                return None
        return None
    if isinstance(val, dict):
        priority_keys = ["value", "price", "amount", "mrp", "cost", "num", "val"]
        for key in priority_keys:
            if key in val and val[key] is not None:
                res = _normalize_numeric_price(val[key])
                if res is not None:
                    return res
        for sub_v in val.values():
            res = _normalize_numeric_price(sub_v)
            if res is not None:
                return res
        return None
    return None


def _normalize_confidence_map(conf: Any) -> Dict[str, float]:
    """
    Normalizes confidence dictionary, handling nested score objects like {'score': 0.92}.
    """
    if not isinstance(conf, dict):
        return {}
    normalized: Dict[str, float] = {}
    for k, v in conf.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            score = float(v)
        elif isinstance(v, dict):
            score = 0.0
            for score_key in ["score", "confidence", "value", "prob", "val"]:
                if score_key in v and isinstance(v[score_key], (int, float)):
                    score = float(v[score_key])
                    break
        elif isinstance(v, str):
            try:
                score = float(v)
            except ValueError:
                score = 0.0
        else:
            score = 0.0
        normalized[str(k)] = max(0.0, min(1.0, round(score, 2)))
    return normalized


def _normalize_warnings_list(raw_warn: Any) -> List[str]:
    """
    Normalizes warnings into a list of strings.
    """
    if isinstance(raw_warn, list):
        return [str(w).strip() for w in raw_warn if w and str(w).strip()]
    if isinstance(raw_warn, str) and raw_warn.strip():
        return [raw_warn.strip()]
    if isinstance(raw_warn, dict):
        return [str(v).strip() for v in raw_warn.values() if v and str(v).strip()]
    return []


def normalize_raw_mistral_json(raw_json: Any) -> Dict[str, Any]:
    """
    Pre-processes and sanitizes Mistral Vision JSON before strict Pydantic validation.
    Converts nested structures into the exact scalar types expected by MistralRawExtraction.
    """
    if not isinstance(raw_json, dict):
        return {
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
            "warnings": ["Vision model returned a non-dictionary JSON response."],
        }

    warnings = _normalize_warnings_list(raw_json.get("warnings"))
    manufacturer = _normalize_manufacturer(raw_json.get("manufacturer"))

    normalized: Dict[str, Any] = {
        "product_name": _normalize_string_field(
            raw_json.get("product_name"),
            ["name", "product_name", "title", "value", "text"],
        ),
        "manufacturer": manufacturer,
        "category": _normalize_string_field(
            raw_json.get("category"),
            ["category", "name", "value", "text", "type"],
        ),
        "batch_number": _normalize_string_field(
            raw_json.get("batch_number"),
            ["value", "batch", "batch_number", "lot", "number", "text"],
        ),
        "manufacturing_date": _normalize_string_field(
            raw_json.get("manufacturing_date"),
            ["value", "date", "mfg", "manufacturing_date", "pkd", "text"],
        ),
        "expiry_date": _normalize_string_field(
            raw_json.get("expiry_date"),
            ["value", "date", "exp", "expiry_date", "use_by", "best_before", "text"],
        ),
        "expiry_text": _normalize_string_field(
            raw_json.get("expiry_text"),
            ["value", "text", "expiry_text", "raw", "date"],
        ),
        "mrp": _normalize_numeric_price(raw_json.get("mrp")),
        "base_cost_price": _normalize_numeric_price(raw_json.get("base_cost_price")),
        "confidence": _normalize_confidence_map(raw_json.get("confidence")),
        "warnings": warnings,
    }

    return normalized


def _find_mistral_api_key() -> Optional[str]:
    """Retrieves Mistral API key from environment variables or settings."""
    key = os.environ.get("MISTRAL_API_KEY")
    if key and key.strip():
        return key.strip()

    if getattr(settings, "mistral_api_key", None) and settings.mistral_api_key.strip():
        return settings.mistral_api_key.strip()

    # Check .env file directly if present
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("MISTRAL_API_KEY="):
                        val = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass
    return None


def get_mistral_model() -> str:
    """Returns the configured Mistral model name."""
    return (
        os.environ.get("MISTRAL_MODEL")
        or getattr(settings, "mistral_model", None)
        or "ministral-14b-2512"
    )


def validate_and_preprocess_image(
    image_bytes: bytes,
    mime_type: Optional[str] = None,
    max_dim: int = 1600,
    jpeg_quality: int = 88,
) -> Tuple[bytes, str, Tuple[int, int], Tuple[int, int]]:
    """
    Validates, resizes (preserving aspect ratio up to max_dim), and compresses image.
    Returns: (optimized_bytes, mime_type, original_dimensions, optimized_dimensions)
    """
    if not image_bytes or len(image_bytes) == 0:
        raise ImageProcessingError("No image data provided or image file is empty.")

    # Validate MIME type if provided
    if mime_type:
        clean_mime = mime_type.lower().split(";")[0].strip()
        allowed_mimes = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if clean_mime not in allowed_mimes:
            raise ImageProcessingError(
                f"Unsupported image format '{mime_type}'. Supported formats: JPEG, PNG, WEBP."
            )

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ImageProcessingError(
                "Unable to decode the uploaded image. File may be corrupt or not a valid image."
            )

        orig_h, orig_w = img.shape[:2]

        # Resize only if exceeding maximum allowed dimension
        if max(orig_h, orig_w) > max_dim:
            scale = max_dim / float(max(orig_h, orig_w))
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            resized = img
            new_w, new_h = orig_w, orig_h

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        success, enc_buf = cv2.imencode(".jpg", resized, encode_param)
        if not success:
            raise ImageProcessingError("Failed to encode image to JPEG.")

        opt_bytes = enc_buf.tobytes()
        return opt_bytes, "image/jpeg", (orig_w, orig_h), (new_w, new_h)

    except ImageProcessingError:
        raise
    except Exception as e:
        logger.error(f"Image preprocessing exception: {e}", exc_info=True)
        raise ImageProcessingError(f"Image processing error: {str(e)}") from e


def normalize_date_string(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes varied date formats (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, MM/YYYY) into YYYY-MM-DD.
    If only month/year is present (MM/YYYY), returns (None, original_text) without inventing a day.
    Returns: (normalized_date_iso_or_none, raw_text_or_none)
    """
    if not date_str or not isinstance(date_str, str):
        return None, None

    cleaned = date_str.strip()
    if not cleaned:
        return None, None

    # Check for Month/Year only: MM/YYYY or MM-YYYY
    mm_yyyy_match = re.fullmatch(r"(\d{1,2})[/-](\d{4})", cleaned)
    if mm_yyyy_match:
        return None, cleaned

    # Check for Month/Year with word: "Aug 2027", "August 2027"
    for fmt in ["%b %Y", "%B %Y", "%b-%Y", "%B-%Y"]:
        try:
            datetime.strptime(cleaned, fmt)
            return None, cleaned
        except ValueError:
            pass

    # Check standard explicit dates: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD, YYYY/MM/DD
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            # Normalize 2-digit years
            if parsed.year < 100:
                year = 2000 + parsed.year
                parsed = parsed.replace(year=year)
            return parsed.strftime("%Y-%m-%d"), cleaned
        except ValueError:
            continue

    # Attempt regex extraction if embedded in text (e.g., "PKD: 15/08/2026")
    embed_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", cleaned)
    if embed_match:
        d, m, y = embed_match.groups()
        try:
            parsed = datetime.strptime(f"{d}-{m}-{y}", "%d-%m-%Y")
            return parsed.strftime("%Y-%m-%d"), cleaned
        except ValueError:
            pass

    return None, cleaned


def calculate_relative_expiry(
    mfg_date_str: Optional[str],
    duration_months: int,
) -> Optional[str]:
    """
    Calculates expiry date given an exact manufacturing date and a duration in months.
    """
    if not mfg_date_str:
        return None
    try:
        mfg = datetime.strptime(mfg_date_str, "%Y-%m-%d")
        month = mfg.month - 1 + duration_months
        year = mfg.year + month // 12
        month = month % 12 + 1
        max_days = calendar.monthrange(year, month)[1]
        day = min(mfg.day, max_days)
        exp = datetime(year, month, day)
        return exp.strftime("%Y-%m-%d")
    except Exception:
        return None


def call_mistral_vision_api(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    timeout: float = 35.0,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Calls the official Mistral API with image_url base64 payload and requests strict JSON output.
    """
    api_key = _find_mistral_api_key()
    if not api_key:
        raise MistralConfigError(
            "MISTRAL_API_KEY is not configured. "
            "Please set MISTRAL_API_KEY in your environment or .env file."
        )

    model = get_mistral_model()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:{mime_type};base64,{b64_image}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": MISTRAL_VISION_PROMPT},
                    {"type": "image_url", "image_url": data_uri},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            logger.info(
                f"[Mistral Vision] Calling model '{model}' "
                f"(attempt {attempt + 1}/{max_retries + 1})..."
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.post(MISTRAL_API_ENDPOINT, json=payload, headers=headers)

            if response.status_code == 200:
                res_json = response.json()
                choices = res_json.get("choices", [])
                if not choices:
                    raise MistralAPIError("Mistral Vision returned an empty choices list.")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise MistralAPIError("Mistral Vision returned empty content in response.")

                cleaned_content = content.strip()
                if cleaned_content.startswith("```"):
                    lines = cleaned_content.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_content = "\n".join(lines).strip()

                parsed_json = json.loads(cleaned_content)
                logger.info(
                    "[Mistral Vision] Successfully received and parsed structured response."
                )
                return parsed_json

            # Handle specific HTTP error status codes
            if response.status_code in [401, 403]:
                logger.error(
                    f"[Mistral Vision] Authentication failed (status {response.status_code})."
                )
                raise MistralConfigError("Invalid or unauthorized Mistral API key.")

            if response.status_code == 429:
                logger.warning(f"[Mistral Vision] Rate limited (429) on attempt {attempt + 1}.")
                if attempt < max_retries:
                    sleep_sec = 2.0 * (attempt + 1)
                    time.sleep(sleep_sec)
                    continue
                raise MistralRateLimitError(
                    "Mistral API rate limit reached. Please retry in a few moments."
                )

            if response.status_code in [500, 502, 503, 504]:
                logger.warning(
                    f"[Mistral Vision] Upstream server error ({response.status_code}) "
                    f"on attempt {attempt + 1}."
                )
                if attempt < max_retries:
                    sleep_sec = 2.0 * (attempt + 1)
                    time.sleep(sleep_sec)
                    continue
                raise MistralAPIError(
                    f"Mistral Vision API server error ({response.status_code})."
                )

            if response.status_code == 413:
                raise ImageProcessingError(
                    "Image payload is too large for Mistral API (413 Payload Too Large)."
                )

            if response.status_code in [400, 422]:
                logger.error(
                    f"[Mistral Vision] Client error ({response.status_code}): "
                    f"{response.text[:300]}"
                )
                raise MistralAPIError(
                    f"Mistral Vision request validation failed: {response.text[:200]}"
                )

            raise MistralAPIError(
                f"Mistral Vision returned status {response.status_code}: {response.text[:200]}"
            )

        except httpx.TimeoutException as e:
            logger.warning(f"[Mistral Vision] Request timeout on attempt {attempt + 1}: {e}")
            if attempt < max_retries:
                time.sleep(1.5)
                continue
            raise MistralTimeoutError("Mistral Vision API request timed out.") from e

        except (httpx.NetworkError, httpx.ConnectError) as e:
            logger.warning(
                f"[Mistral Vision] Network connection error on attempt {attempt + 1}: {e}"
            )
            if attempt < max_retries:
                time.sleep(2.0)
                continue
            raise MistralAPIError(
                f"Network error communicating with Mistral Vision API: {e}"
            ) from e

        except json.JSONDecodeError as e:
            logger.error(f"[Mistral Vision] Malformed JSON in model response: {e}")
            raise MistralAPIError(
                f"Failed to parse structured JSON from Mistral Vision response: {e}"
            ) from e

        except MistralVisionError:
            raise
        except Exception as e:
            last_error = e
            logger.error(f"[Mistral Vision] Unexpected error during API call: {e}", exc_info=True)

    raise MistralAPIError(
        f"Mistral Vision call failed after {max_retries + 1} attempts: {last_error}"
    )


def extract_product_information(
    image_bytes: bytes,
    mime_type: Optional[str] = None,
) -> OcrExtractionResult:
    """
    Main entry point for product packaging extraction using Mistral Vision API.
    """
    t_start = time.time()

    # 1. Image Preprocessing
    opt_bytes, opt_mime, orig_dims, opt_dims = validate_and_preprocess_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        max_dim=1600,
        jpeg_quality=88,
    )
    logger.info(
        f"[Mistral Vision] Image preprocessed: {orig_dims[0]}x{orig_dims[1]} -> "
        f"{opt_dims[0]}x{opt_dims[1]} (JPEG)"
    )

    # 2. Call Mistral Vision API
    raw_data = call_mistral_vision_api(
        image_bytes=opt_bytes,
        mime_type=opt_mime,
        timeout=35.0,
        max_retries=2,
    )

    # 3. Sanitize and Validate with Pydantic
    sanitized_data = normalize_raw_mistral_json(raw_data)
    try:
        validated = MistralRawExtraction(**sanitized_data)
    except Exception as e:
        logger.error(f"[Mistral Vision] Pydantic schema validation error: {e}", exc_info=True)
        raise MistralAPIError(f"Mistral extraction schema validation failed: {e}") from e

    warnings = list(validated.warnings or [])
    conflicts: List[str] = []

    # 4. Normalize Dates
    mfg_date_iso, mfg_raw = normalize_date_string(validated.manufacturing_date)
    exp_date_iso, exp_raw = normalize_date_string(validated.expiry_date)

    if validated.expiry_text and not exp_raw:
        exp_raw = validated.expiry_text

    # If expiry was not parsed as ISO, check if it's Month/Year
    if validated.expiry_date and not exp_date_iso and exp_raw:
        warnings.append(
            f"Expiry date was detected as '{exp_raw}'. Please specify the exact day manually."
        )

    # Check for relative expiry duration in warnings / text if expiry_date is null
    if not exp_date_iso and mfg_date_iso and exp_raw:
        duration_match = re.search(r"(\d+)\s*(?:months|month)", exp_raw, re.IGNORECASE)
        if duration_match:
            months = int(duration_match.group(1))
            calculated = calculate_relative_expiry(mfg_date_iso, months)
            if calculated:
                exp_date_iso = calculated
                warnings.append(
                    f"Expiry date calculated as {calculated} based on '{exp_raw}' "
                    f"from manufacturing date."
                )

    if not exp_date_iso and not validated.expiry_date:
        warnings.append(
            "Expiry date could not be confidently read from the image. Please verify manually."
        )

    # Check date ordering
    if mfg_date_iso and exp_date_iso:
        try:
            mfg_dt = datetime.strptime(mfg_date_iso, "%Y-%m-%d")
            exp_dt = datetime.strptime(exp_date_iso, "%Y-%m-%d")
            if mfg_dt > exp_dt:
                conflicts.append(
                    f"Manufacturing date ({mfg_date_iso}) is after Expiry date ({exp_date_iso})."
                )
        except Exception:
            pass

    # 5. Normalize Prices
    mrp_val = validated.mrp
    base_price_val = validated.base_cost_price if validated.base_cost_price is not None else mrp_val

    # 6. Normalize Confidence Scores
    raw_conf = validated.confidence or {}
    confidence_map: Dict[str, float] = {}

    def get_conf(field_key: str, val: Any) -> float:
        if val is None or val == "":
            return 0.0
        c = float(raw_conf.get(field_key, 0.85))
        return max(0.0, min(1.0, round(c, 2)))

    confidence_map["product_name"] = get_conf("product_name", validated.product_name)
    confidence_map["manufacturer"] = get_conf("manufacturer", validated.manufacturer)
    confidence_map["category"] = get_conf("category", validated.category)
    confidence_map["batch_number"] = get_conf("batch_number", validated.batch_number)
    confidence_map["manufacturing_date"] = get_conf("manufacturing_date", mfg_date_iso)
    confidence_map["expiry_date"] = get_conf("expiry_date", exp_date_iso)
    confidence_map["mrp"] = get_conf("mrp", mrp_val)
    confidence_map["base_price"] = get_conf("base_cost_price", base_price_val)
    confidence_map["sku"] = 0.0

    non_zero_confs = [c for c in confidence_map.values() if c > 0.0]
    overall_conf = round(sum(non_zero_confs) / len(non_zero_confs), 2) if non_zero_confs else 0.0

    # Build FieldExtraction dictionaries
    semantic_fields: Dict[str, FieldExtraction] = {}
    fields_dict: Dict[str, Any] = {
        "product_name": validated.product_name,
        "manufacturer": validated.manufacturer,
        "category": validated.category,
        "batch_number": validated.batch_number,
        "manufacturing_date": mfg_date_iso,
        "expiry_date": exp_date_iso,
        "mrp": mrp_val,
        "base_price": base_price_val,
        "sku": None,
    }

    for k, v in fields_dict.items():
        semantic_fields[k] = FieldExtraction(
            value=v,
            confidence=confidence_map.get(k, 0.0),
            source="mistral-vision",
        )

    # 7. Return OcrExtractionResult
    raw_summary = (
        f"Product: {validated.product_name or ''}\n"
        f"Batch: {validated.batch_number or ''}\n"
        f"Expiry: {exp_raw or exp_date_iso or ''}\n"
        f"MRP: {mrp_val or ''}"
    )

    result = OcrExtractionResult(
        success=True,
        ocr_engine="mistral-vision",
        semantic_engine="mistral-vision",
        fallback_used=False,
        overall_confidence=overall_conf,
        product_name=validated.product_name,
        manufacturer=validated.manufacturer,
        category=validated.category,
        sku=None,
        batch_number=validated.batch_number,
        manufacturing_date=mfg_date_iso,
        expiry_date=exp_date_iso,
        mrp=mrp_val,
        base_price=base_price_val,
        fields=fields_dict,
        semantic_fields=semantic_fields,
        confidence=confidence_map,
        raw_text=raw_summary,
        warnings=warnings,
        conflicts=conflicts,
    )

    t_total = time.time() - t_start
    logger.info(f"[Mistral Vision] Extraction completed successfully in {t_total*1000:.1f} ms.")
    return result
