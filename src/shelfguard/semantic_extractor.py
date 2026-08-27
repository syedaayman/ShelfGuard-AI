import base64
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from shelfguard.config import settings

logger = logging.getLogger(__name__)


class SemanticExtractionError(Exception):
    """Base exception for semantic vision extraction failures."""
    pass


class SemanticConfigError(SemanticExtractionError):
    """Raised when GEMINI_API_KEY is missing or invalid."""
    pass


class SemanticRateLimitError(SemanticExtractionError):
    """Raised when free-tier rate limits or quotas are exceeded."""
    pass


SEMANTIC_SYSTEM_PROMPT = """You are an expert product-packaging semantic analysis AI.
You are extracting structured product information from a single real-world product packaging photo.
Inspect the image itself — OCR text is supporting evidence only and may contain errors.
Do not blindly trust OCR output.

Identify:
- PRODUCT NAME (the actual brand/item identity — NEVER a field label like DATE, EXP, MRP, BATCH)
- MANUFACTURER / BRAND NAME
- BATCH / LOT NUMBER (require explicit labels like BATCH, LOT, B.NO — NEVER a date)
- MANUFACTURING DATE (in strict YYYY-MM-DD format if present)
- EXPIRY DATE / USE BY / BEST BEFORE (in strict YYYY-MM-DD format if present)
- MRP (maximum retail price as float, only if explicitly labeled as MRP/Price — NEVER random)
- BASE PRICE (if explicitly distinguished from MRP, otherwise null)
- CATEGORY (e.g. Dairy, Pickles, Beverages, Bakery, Snacks, etc.)

Strict Rules:
1. Never assume an arbitrary number is a date (e.g. '250', '500g', '180' are not dates).
2. Never classify a number as MFG or EXP without explicit contextual evidence.
3. If multiple dates exist and meaning is unclear, return them in 'conflicts' or 'warnings'.
4. Do not infer expiry simply because one date is later than another.
5. If expiry is expressed as a duration (e.g. '12 months from manufacture'):
   - If manufacturing date is present, calculate exact expiry date YYYY-MM-DD.
   - If manufacturing date is missing, set expiry_date to null and add duration rule to warnings.
6. Provide a confidence score between 0.0 and 1.0 for every extracted field.
7. Return ONLY valid JSON conforming to the schema.
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "product_name": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            },
            "required": ["value", "confidence"]
        },
        "manufacturer": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "batch_number": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "manufacturing_date": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "expiry_date": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            },
            "required": ["value", "confidence"]
        },
        "mrp": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "NUMBER"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "base_price": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "NUMBER"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "category": {
            "type": "OBJECT",
            "properties": {
                "value": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
                "source": {"type": "STRING"}
            }
        },
        "warnings": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "conflicts": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        }
    },
    "required": ["product_name", "expiry_date"]
}


def _find_gemini_api_key() -> Optional[str]:
    # 1. Check live environment variable first (call-time)
    key = os.environ.get("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    # 2. Check Pydantic settings
    if settings.gemini_api_key and settings.gemini_api_key.strip():
        return settings.gemini_api_key.strip()

    # 3. Check root .env and frontend/.env dynamically
    for env_path in [".env", "frontend/.env", "../frontend/.env"]:
        if os.path.isfile(env_path):
            try:
                from dotenv import dotenv_values
                vals = dotenv_values(env_path)
                found = vals.get("GEMINI_API_KEY")
                if found and found.strip():
                    return found.strip()
            except Exception:
                pass
    return None


def _get_api_key() -> str:
    api_key = _find_gemini_api_key()
    if not api_key:
        raise SemanticConfigError(
            "GEMINI_API_KEY is not configured. "
            "Please set GEMINI_API_KEY in your environment or .env file."
        )
    return api_key


def extract_semantic_data(
    image_bytes: bytes,
    raw_ocr_lines: List[str],
    mime_type: str = "image/jpeg",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Calls Google Gemini Flash-tier Vision API with image and supporting OCR text.
    Implements exponential backoff with jitter on 429/503 for free-tier resilience.
    """
    api_key = _get_api_key()
    model = os.environ.get("GEMINI_MODEL") or settings.gemini_model or "gemini-3.6-flash"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    endpoint = f"{base_url}/{model}:generateContent?key={api_key}"

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    ocr_context = "\n".join(raw_ocr_lines) if raw_ocr_lines else "(No text detected by OCR)"

    user_prompt = (
        f"Supporting raw EasyOCR text detected from packaging:\n"
        f"```\n{ocr_context}\n```\n\n"
        f"Analyze attached packaging photo carefully. Extract fields into required JSON schema."
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": SEMANTIC_SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_image
                        }
                    },
                    {
                        "text": user_prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
            "responseSchema": RESPONSE_SCHEMA
        }
    }

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            logger.info(
                f"Calling Gemini Vision ({model}) for semantic packaging "
                f"interpretation (attempt {attempt + 1}/{max_retries})..."
            )
            with httpx.Client(timeout=45.0) as client:
                response = client.post(endpoint, json=payload)

            if response.status_code == 200:
                resp_json = response.json()
                try:
                    candidates = resp_json.get("candidates", [])
                    if not candidates:
                        raise SemanticExtractionError(
                            "Gemini Vision returned an empty candidates list."
                        )

                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    if not content_parts:
                        raise SemanticExtractionError(
                            "Gemini Vision returned an empty content part."
                        )

                    raw_content = content_parts[0].get("text", "{}")
                    parsed_data = json.loads(raw_content)
                    logger.info("Semantic extraction completed successfully via Gemini Vision.")
                    return parsed_data
                except Exception as parse_err:
                    logger.error(
                        f"Failed to parse Gemini Vision JSON: {parse_err}. "
                        f"Body: {response.text}"
                    )
                    raise SemanticExtractionError(
                        f"Failed to parse semantic model output: {parse_err}"
                    ) from parse_err

            elif response.status_code in [429, 503]:
                sleep_time = (1.5 ** attempt) * 2.0 + random.uniform(0.5, 1.5)
                logger.warning(
                    f"Gemini API returned status {response.status_code}. "
                    f"Backing off for {sleep_time:.2f}s before retry..."
                )
                time.sleep(sleep_time)
                last_error = SemanticRateLimitError(
                    "Semantic extraction service is busy (free-tier rate limit reached). "
                    "Please retry in a moment."
                )
            elif response.status_code == 400:
                logger.error(f"Gemini Vision client error (400): {response.text}")
                raise SemanticExtractionError(
                    f"Invalid request to Gemini Vision API: {response.text}"
                )
            elif response.status_code == 403:
                logger.error(f"Gemini Vision authorization error (403): {response.text}")
                raise SemanticConfigError(
                    "Gemini API key is invalid or lacks necessary permissions."
                )
            else:
                logger.error(
                    f"Gemini Vision returned unexpected status {response.status_code}: "
                    f"{response.text}"
                )
                raise SemanticExtractionError(
                    f"Semantic vision service error (HTTP {response.status_code}): "
                    f"{response.text}"
                )

        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.warning(f"Network error communicating with Gemini Vision: {net_err}.")
            sleep_time = (1.5 ** attempt) * 1.5 + random.uniform(0.3, 1.0)
            time.sleep(sleep_time)
            last_error = SemanticExtractionError(
                f"Network timeout communicating with semantic extraction service: {net_err}"
            )
        except SemanticExtractionError:
            raise
        except Exception as general_err:
            logger.error(f"Unexpected error in semantic extractor: {general_err}", exc_info=True)
            raise SemanticExtractionError(
                f"Unexpected error during semantic extraction: {general_err}"
            ) from general_err

    if last_error:
        raise last_error

    raise SemanticExtractionError("Semantic extraction failed after maximum retries.")
