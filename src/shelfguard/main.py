import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, List, Optional

import joblib
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi import status as fastapi_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from shelfguard.config import settings
from shelfguard.database import (
    BUSINESS_TIMEZONE,
    InventoryBatch,
    NgoDonation,
    Product,
    calculate_expiry_status,
    find_existing_batch,
    generate_internal_batch_id,
    get_db,
    init_db,
    resolve_product,
)
from shelfguard.mistral_vision import (
    ImageProcessingError,
    MistralAPIError,
    MistralConfigError,
    MistralRateLimitError,
    MistralTimeoutError,
    _find_mistral_api_key,
    extract_product_information,
    get_mistral_model,
)
from shelfguard.ngo_router import (
    create_donation_requests,
    process_pending_donations,
    route_donation,
    scan_for_near_expiry,
)
from shelfguard.pricing_engine import (
    calculate_dynamic_discount_batch,
    calculate_single_discount,
)
from shelfguard.schemas import (
    BatchCreateRequest,
    BatchResponse,
    CategoryShareItem,
    CategoryShareResponse,
    DashboardStatsResponse,
    DashboardTrendsResponse,
    DonationCandidate,
    DonationCreateRequest,
    DonationRecord,
    InventoryItemResponse,
    InventoryListResponse,
    NgoDispatchRequest,
    OcrExtractionResult,
    PricingRequest,
    PricingResponse,
    ProductResponse,
    TaxLedgerInsertRequest,
    TaxLedgerResponse,
    TaxRequest,
    TaxResponse,
    TrendStageMetric,
)
from shelfguard.tax_ledger import TaxCalculator, TaxLedgerManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global ML instances
ml_model: Any = None
feature_names: list = []

MAX_UPLOAD_SIZE = 15 * 1024 * 1024  # 15 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_model, feature_names
    try:
        init_db()
        logger.info(f"Loading pricing model from {settings.model_path}")
        ml_model = joblib.load(settings.model_path)
        app.state.ml_model = ml_model
        feature_names_path = settings.model_path.replace(
            "xgboost_pricing_model.joblib", "feature_names.json"
        )
        with open(feature_names_path, "r", encoding="utf-8") as f:
            feature_names = json.load(f)

        expected_features = ["remaining_hours", "base_price", "initial_quantity", "daily_demand"]
        if feature_names != expected_features:
            raise ValueError(
                f"Model feature mismatch. Expected {expected_features}, got {feature_names}"
            )

        # Log MISTRAL_API_KEY configuration status at server boot
        api_key = _find_mistral_api_key()
        model = get_mistral_model()
        if api_key:
            masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
            logger.info(
                f"Mistral Vision API: Configured successfully (Model: {model}, Key: {masked_key})."
            )
        else:
            logger.warning(
                "Mistral Vision API: MISTRAL_API_KEY is NOT detected in environment or .env file."
            )

        logger.info("Lifespan setup completed successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize server lifespan: {e}", exc_info=True)
        raise RuntimeError("API startup failed: Could not load the pricing model.") from e
    yield
    ml_model = None


app = FastAPI(title="ShelfGuard AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/inventory", response_model=InventoryListResponse)
def list_inventory(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        process_pending_donations(db)

        query = db.query(InventoryBatch, Product).join(
            Product, InventoryBatch.product_id == Product.id
        )

        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                (Product.sku.ilike(search_pattern))
                | (Product.product_name.ilike(search_pattern))
                | (Product.category.ilike(search_pattern))
                | (Product.manufacturer.ilike(search_pattern))
                | (InventoryBatch.batch_number.ilike(search_pattern))
            )

        all_results = query.order_by(Product.sku, InventoryBatch.expiry_date).all()

        target_status = (status_filter or status or "").strip().upper()
        if target_status == "ALL":
            target_status = ""

        batch_items_data = []
        raw_items_meta = []
        for batch, product in all_results:
            exp_info = calculate_expiry_status(batch.expiry_date)
            dyn_status = exp_info["status"]

            if target_status and dyn_status != target_status:
                continue

            ref_price = float(product.mrp if product.mrp is not None else product.base_price)
            batch_items_data.append(
                {
                    "remaining_hours": exp_info["remaining_hours"],
                    "base_price": ref_price,
                    "stock_quantity": batch.stock_quantity,
                    "daily_demand": batch.daily_demand,
                    "expiry_status": dyn_status,
                }
            )
            raw_items_meta.append((batch, product, exp_info, dyn_status, ref_price))

        active_model = getattr(app.state, "ml_model", None) or ml_model
        pricing_results = calculate_dynamic_discount_batch(active_model, batch_items_data)

        filtered_items = []
        for i, (batch, product, exp_info, dyn_status, ref_price) in enumerate(raw_items_meta):
            pr = pricing_results[i]
            filtered_items.append(
                InventoryItemResponse(
                    sku=product.sku,
                    product_name=product.product_name,
                    category=product.category,
                    manufacturer=product.manufacturer,
                    base_price=product.base_price,
                    mrp=product.mrp,
                    batch_number=batch.batch_number,
                    internal_batch_id=batch.internal_batch_id,
                    manufacturing_date=batch.manufacturing_date,
                    expiry_date=batch.expiry_date,
                    stock_quantity=batch.stock_quantity,
                    current_discount=batch.current_discount,
                    daily_demand=batch.daily_demand,
                    status=dyn_status,
                    remaining_hours=exp_info["remaining_hours"],
                    remaining_days=exp_info["remaining_days"],
                    remaining_text=exp_info["remaining_text"],
                    dynamic_discount_percent=pr["dynamic_discount_percent"],
                    dynamic_discount_fraction=pr["dynamic_discount_fraction"],
                    final_price=pr["final_price"],
                    is_override=pr["is_override"],
                    override_reason=pr["override_reason"],
                    updated_at=batch.updated_at,
                )
            )

        total = len(filtered_items)
        paginated_items = filtered_items[offset : offset + limit]

        return {"items": paginated_items, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Inventory list error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.get("/inventory/{sku}", response_model=ProductResponse)
def get_inventory(sku: str, db: Session = Depends(get_db)):
    try:
        process_pending_donations(db)
        product = db.query(Product).filter(Product.sku == sku.strip().upper()).first()
        if not product:
            product = db.query(Product).filter(Product.sku.ilike(sku.strip())).first()
        if not product:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail="SKU not found",
            )

        batch_items_data = []
        raw_batches_meta = []
        for batch in product.batches:
            exp_info = calculate_expiry_status(batch.expiry_date)
            ref_price = product.mrp if product.mrp is not None else product.base_price
            batch_items_data.append(
                {
                    "remaining_hours": exp_info["remaining_hours"],
                    "base_price": ref_price,
                    "stock_quantity": batch.stock_quantity,
                    "daily_demand": batch.daily_demand,
                    "expiry_status": exp_info["status"],
                }
            )
            raw_batches_meta.append((batch, exp_info))

        active_model = getattr(app.state, "ml_model", None) or ml_model
        pricing_results = calculate_dynamic_discount_batch(active_model, batch_items_data)

        batch_responses = []
        for i, (batch, exp_info) in enumerate(raw_batches_meta):
            pr = pricing_results[i]
            batch_responses.append(
                BatchResponse(
                    id=batch.id,
                    product_id=batch.product_id,
                    batch_number=batch.batch_number,
                    internal_batch_id=batch.internal_batch_id,
                    manufacturing_date=batch.manufacturing_date,
                    expiry_date=batch.expiry_date,
                    stock_quantity=batch.stock_quantity,
                    current_discount=batch.current_discount,
                    daily_demand=batch.daily_demand,
                    status=exp_info["status"],
                    remaining_hours=exp_info["remaining_hours"],
                    remaining_days=exp_info["remaining_days"],
                    remaining_text=exp_info["remaining_text"],
                    dynamic_discount_percent=pr["dynamic_discount_percent"],
                    dynamic_discount_fraction=pr["dynamic_discount_fraction"],
                    final_price=pr["final_price"],
                    is_override=pr["is_override"],
                    override_reason=pr["override_reason"],
                    created_at=batch.created_at,
                    updated_at=batch.updated_at,
                )
            )

        return ProductResponse(
            id=product.id,
            sku=product.sku,
            product_name=product.product_name,
            category=product.category,
            manufacturer=product.manufacturer,
            base_price=product.base_price,
            mrp=product.mrp,
            created_at=product.created_at,
            updated_at=product.updated_at,
            batches=batch_responses,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/ocr/scan", response_model=OcrExtractionResult)
async def scan_ocr(image: Optional[UploadFile] = File(None)):
    """
    Scans a single product packaging image using the official Mistral Vision API (Ministral 3 14B).
    """
    if not image or not image.filename:
        raise HTTPException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No image was provided. Please upload a product packaging image.",
        )

    content_type = image.content_type or ""
    clean_type = content_type.lower().split(";")[0].strip()
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if clean_type not in allowed_types and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=fastapi_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Uploaded file must be a supported image format (JPEG, PNG, WEBP). "
                f"Received '{content_type}'."
            ),
        )

    try:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=fastapi_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image exceeds the maximum allowed size of 15 MB.",
            )

        result = extract_product_information(image_bytes, mime_type=content_type)
        return result

    except HTTPException:
        raise
    except ImageProcessingError as e:
        logger.warning(f"[Scanner] Image processing error: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MistralConfigError as e:
        logger.error(f"[Scanner] Mistral API configuration error: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_502_BAD_GATEWAY,
            detail=f"Mistral Vision service configuration error: {str(e)}",
        )
    except MistralRateLimitError as e:
        logger.warning(f"[Scanner] Mistral API rate limit: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mistral Vision API rate limit reached (429). Please retry in a moment.",
        )
    except MistralTimeoutError as e:
        logger.warning(f"[Scanner] Mistral API timeout: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Mistral Vision API request timed out. Please try again.",
        )
    except MistralAPIError as e:
        logger.error(f"[Scanner] Mistral API error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_502_BAD_GATEWAY,
            detail=f"Mistral Vision API service error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"[Scanner] Unexpected error during scan: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process image scan due to an unexpected error.",
        )


@app.post("/inventory/batches", response_model=BatchResponse)
def create_or_update_batch(request: BatchCreateRequest, db: Session = Depends(get_db)):
    # 1. Validation
    if not request.product_name or not request.product_name.strip():
        raise HTTPException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product name is required.",
        )

    if not request.expiry_date or not request.expiry_date.strip():
        raise HTTPException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expiry date is required.",
        )

    try:
        exp_dt = datetime.strptime(request.expiry_date.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid expiry date format: '{request.expiry_date}'. Expected YYYY-MM-DD.",
        )

    if request.manufacturing_date and request.manufacturing_date.strip():
        try:
            mfg_dt = datetime.strptime(request.manufacturing_date.strip(), "%Y-%m-%d")
            if mfg_dt > exp_dt:
                raise HTTPException(
                    status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Manufacturing date cannot be later than expiry date.",
                )
        except ValueError:
            raise HTTPException(
                status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid manufacturing date format: '{request.manufacturing_date}'. "
                    "Expected YYYY-MM-DD."
                ),
            )

    if request.stock_quantity <= 0:
        raise HTTPException(
            status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stock quantity must be greater than zero.",
        )

    try:
        # 2. Resolve Product
        product = resolve_product(
            db=db,
            sku=request.sku,
            product_name=request.product_name,
            manufacturer=request.manufacturer,
            base_price=request.base_price,
            mrp=request.mrp,
            category=request.category,
        )

        clean_batch_no = request.batch_number.strip() if request.batch_number else None
        clean_mfg = request.manufacturing_date.strip() if request.manufacturing_date else None
        clean_exp = request.expiry_date.strip()

        # 3. Batch Matching
        existing_batch = find_existing_batch(
            db=db,
            product_id=product.id,
            batch_number=clean_batch_no,
            expiry_date=clean_exp,
            manufacturing_date=clean_mfg,
        )

        if existing_batch:
            if not request.confirm_existing and not request.force_new_batch:
                # Existing batch found -> return 409 Conflict with batch metadata
                db.rollback()
                return JSONResponse(
                    status_code=fastapi_status.HTTP_409_CONFLICT,
                    content={
                        "detail": (
                            f"Existing batch found for '{product.product_name}' "
                            f"(Batch: {existing_batch.batch_number or 'N/A'}, "
                            f"Expiry: {existing_batch.expiry_date}, "
                            f"Current Stock: {existing_batch.stock_quantity}). "
                            "Please choose whether to add stock to this batch or "
                            "create a separate new batch."
                        ),
                        "existing_batch": {
                            "id": existing_batch.id,
                            "product_id": product.id,
                            "product_name": product.product_name,
                            "sku": product.sku,
                            "batch_number": existing_batch.batch_number,
                            "manufacturing_date": existing_batch.manufacturing_date,
                            "expiry_date": existing_batch.expiry_date,
                            "stock_quantity": existing_batch.stock_quantity,
                        },
                    },
                )

            if request.confirm_existing:
                # Add stock to the existing batch record
                existing_batch.stock_quantity += request.stock_quantity
                existing_batch.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing_batch)
                return existing_batch

            if request.force_new_batch:
                # Explicit user choice to create a separate batch
                internal_id = generate_internal_batch_id(
                    sku=product.sku,
                    expiry_date=clean_exp,
                    batch_number=clean_batch_no,
                    unique_suffix=True,
                )
                new_batch = InventoryBatch(
                    product_id=product.id,
                    batch_number=clean_batch_no,
                    internal_batch_id=internal_id,
                    manufacturing_date=clean_mfg,
                    expiry_date=clean_exp,
                    stock_quantity=request.stock_quantity,
                    daily_demand=0,
                    status="ACTIVE",
                )
                db.add(new_batch)
                db.commit()
                db.refresh(new_batch)
                return new_batch

        # 4. No existing batch -> Create new batch
        internal_id = generate_internal_batch_id(
            sku=product.sku,
            expiry_date=clean_exp,
            batch_number=clean_batch_no,
        )
        new_batch = InventoryBatch(
            product_id=product.id,
            batch_number=clean_batch_no,
            internal_batch_id=internal_id,
            manufacturing_date=clean_mfg,
            expiry_date=clean_exp,
            stock_quantity=request.stock_quantity,
            daily_demand=0,
            status="ACTIVE",
        )
        db.add(new_batch)
        db.commit()
        db.refresh(new_batch)
        return new_batch

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Batch creation/update error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save batch to database.",
        )


@app.post("/pricing/recommend", response_model=PricingResponse)
def recommend_pricing(request: PricingRequest):
    try:
        active_model = getattr(app.state, "ml_model", None) or ml_model
        pr = calculate_single_discount(
            ml_model=active_model,
            remaining_hours=request.remaining_hours,
            base_price=request.base_price,
            stock_quantity=request.initial_quantity,
            daily_demand=request.daily_demand,
            expiry_status="ACTIVE",
        )
        return PricingResponse(
            recommended_discount=pr["dynamic_discount_fraction"],
            dynamic_discount_percent=pr["dynamic_discount_percent"],
            final_price=pr["final_price"],
            is_override=pr["is_override"],
            override_reason=pr["override_reason"],
        )
    except Exception as e:
        logger.error(f"Pricing model error: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/tax/calculate", response_model=TaxResponse)
def calculate_tax(request: TaxRequest):
    try:
        tax_collected = TaxCalculator.calculate_tax(request.taxable_amount, request.tax_rate)
        final_amount = request.taxable_amount + tax_collected
        return TaxResponse(tax_collected=tax_collected, final_amount=final_amount)
    except ValueError as e:
        raise HTTPException(status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Tax calculation error: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/tax-ledger/insert", response_model=TaxLedgerResponse)
def insert_tax_ledger(request: TaxLedgerInsertRequest, db: Session = Depends(get_db)):
    try:
        entry = TaxLedgerManager.insert_ledger_entry(
            db,
            transaction_id=request.transaction_id,
            taxable_amount=request.taxable_amount,
            tax_rate=request.tax_rate,
        )
        return entry
    except ValueError as e:
        raise HTTPException(status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Tax ledger insertion error: {e}")
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.get("/api/dashboard/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(db: Session = Depends(get_db)):
    try:
        process_pending_donations(db)

        batches = db.query(InventoryBatch).all()

        safe_count = 0
        near_expiry_count = 0
        critical_count = 0
        donation_count = 0
        expired_count = 0
        ngo_candidates_count = 0
        donation_units_count = 0

        for batch in batches:
            exp_info = calculate_expiry_status(batch.expiry_date)
            st = exp_info["status"]
            rem_h = exp_info["remaining_hours"]

            if st == "SAFE":
                safe_count += 1
            elif st == "NEAR_EXPIRY":
                near_expiry_count += 1
            elif st == "CRITICAL":
                critical_count += 1
            elif st == "DONATION":
                donation_count += 1
            elif st == "EXPIRED":
                expired_count += 1

            if st == "DONATION" and 0.0 < rem_h <= 6.0 and batch.stock_quantity > 0:
                ngo_candidates_count += 1
                donation_units_count += batch.stock_quantity

        return DashboardStatsResponse(
            total_inventory_items=len(batches),
            safe_count=safe_count,
            near_expiry_count=near_expiry_count,
            critical_count=critical_count,
            donation_count=donation_count,
            expired_count=expired_count,
            ngo_candidates=ngo_candidates_count,
            donation_units_count=donation_units_count,
        )
    except Exception as e:
        logger.error(f"Dashboard stats calculation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.get("/api/dashboard/categories", response_model=CategoryShareResponse)
def get_dashboard_categories(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import func

        # Query total batches and stock units aggregated across the full database
        results = (
            db.query(
                func.coalesce(Product.category, "Uncategorized").label("category"),
                func.count(InventoryBatch.id).label("batch_count"),
                func.coalesce(func.sum(InventoryBatch.stock_quantity), 0).label("total_stock"),
            )
            .join(InventoryBatch, Product.id == InventoryBatch.product_id)
            .group_by(Product.category)
            .order_by(func.count(InventoryBatch.id).desc())
            .all()
        )

        total_batches = sum(row.batch_count for row in results)
        items = []
        for row in results:
            pct = round((row.batch_count / total_batches * 100.0), 1) if total_batches > 0 else 0.0
            items.append(
                CategoryShareItem(
                    category=row.category,
                    count=row.batch_count,
                    total_stock_units=int(row.total_stock),
                    percentage=pct,
                )
            )

        return CategoryShareResponse(
            items=items,
            total_batches=total_batches,
            total_categories=len(items),
        )
    except Exception as e:
        logger.error(f"Dashboard categories calculation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute category analytics",
        )


@app.get("/api/dashboard/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends(db: Session = Depends(get_db)):
    try:
        process_pending_donations(db)

        # Query all live inventory batches with product details
        batch_records = (
            db.query(InventoryBatch, Product)
            .join(Product, InventoryBatch.product_id == Product.id)
            .all()
        )

        if not batch_records:
            return DashboardTrendsResponse(
                stages=[],
                labels=[],
                discount_rates=[],
                demand_velocities=[],
                summary_insight="No inventory batches currently available to evaluate trends.",
            )

        # Prepare vectorized inference payload
        batch_items_data = []
        raw_meta = []
        for batch, product in batch_records:
            exp_info = calculate_expiry_status(batch.expiry_date)
            dyn_status = exp_info["status"]
            rem_h = exp_info["remaining_hours"]
            ref_price = float(product.mrp if product.mrp is not None else product.base_price)

            batch_items_data.append(
                {
                    "remaining_hours": rem_h,
                    "base_price": ref_price,
                    "stock_quantity": batch.stock_quantity,
                    "daily_demand": batch.daily_demand,
                    "expiry_status": dyn_status,
                }
            )
            raw_meta.append((batch, product, rem_h, dyn_status))

        active_model = getattr(app.state, "ml_model", None) or ml_model
        pricing_results = calculate_dynamic_discount_batch(active_model, batch_items_data)

        # Define 5 scientifically structured lifecycle expiry horizons (from Safe to Final Window)
        horizon_defs = [
            ("SAFE", "Safe (> 7d)", lambda h: h > 168.0),
            ("NEAR_EXPIRY", "Near Expiry (2–7d)", lambda h: 48.0 < h <= 168.0),
            ("CRITICAL_MODERATE", "Critical (24h–48h)", lambda h: 24.0 < h <= 48.0),
            ("CRITICAL_URGENT", "Urgent Critical (6h–24h)", lambda h: 6.0 < h <= 24.0),
            ("DONATION_WINDOW", "Donation Window (≤ 6h)", lambda h: 0.0 < h <= 6.0),
        ]

        buckets = {
            key: {"discounts": [], "demands": [], "count": 0, "label": label}
            for key, label, _ in horizon_defs
        }

        for i, (batch, product, rem_h, dyn_status) in enumerate(raw_meta):
            if rem_h <= 0.0:
                continue  # Skip already expired stock from commercial discount progression profile

            pr = pricing_results[i]
            disc_pct = pr["dynamic_discount_percent"]
            demand = batch.daily_demand

            for key, _, matcher in horizon_defs:
                if matcher(rem_h):
                    buckets[key]["discounts"].append(disc_pct)
                    buckets[key]["demands"].append(demand)
                    buckets[key]["count"] += 1
                    break

        stages = []
        labels = []
        discount_rates = []
        demand_velocities = []

        for key, label, _ in horizon_defs:
            b = buckets[key]
            count = b["count"]
            avg_disc = round(sum(b["discounts"]) / count, 1) if count > 0 else 0.0
            avg_dem = round(sum(b["demands"]) / count, 1) if count > 0 else 0.0

            stages.append(
                TrendStageMetric(
                    stage_key=key,
                    stage_label=label,
                    batch_count=count,
                    avg_discount_percent=avg_disc,
                    avg_daily_demand=avg_dem,
                )
            )
            labels.append(label)
            discount_rates.append(avg_disc)
            demand_velocities.append(avg_dem)

        insight = (
            "Profile calculated dynamically from current database inventory batches "
            "evaluating real XGBoost dynamic discounts and sales demand velocity across expiry horizons."
        )

        return DashboardTrendsResponse(
            stages=stages,
            labels=labels,
            discount_rates=discount_rates,
            demand_velocities=demand_velocities,
            summary_insight=insight,
        )
    except Exception as e:
        logger.error(f"Dashboard trends calculation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute dynamic pricing velocity trends",
        )


@app.get("/api/ngo/donations", response_model=List[DonationRecord])
def get_donations(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    try:
        process_pending_donations(db)

        raw_donations = (
            db.query(NgoDonation)
            .order_by(NgoDonation.requested_at.desc(), NgoDonation.donation_id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        now = datetime.now(BUSINESS_TIMEZONE)
        records = []
        for d in raw_donations:
            rem_sec = 0
            if d.status == "PENDING":
                req_at = d.requested_at or d.dispatch_timestamp
                if req_at:
                    if req_at.tzinfo is None:
                        req_at = req_at.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TIMEZONE)
                    else:
                        req_at = req_at.astimezone(BUSINESS_TIMEZONE)
                    elapsed = (now - req_at).total_seconds()
                    rem_sec = max(0, int(120 - elapsed))
                else:
                    rem_sec = 120

            records.append(
                DonationRecord(
                    donation_id=d.donation_id,
                    batch_id=d.batch_id,
                    batch_number=d.batch_number,
                    sku=d.sku,
                    ngo_name=d.ngo_name,
                    product_name=d.product_name,
                    quantity=d.quantity,
                    estimated_value=d.estimated_value,
                    dispatch_timestamp=d.dispatch_timestamp,
                    requested_at=d.requested_at,
                    approved_at=d.approved_at,
                    status=d.status or "PENDING",
                    remaining_seconds_to_approve=rem_sec,
                    tax_receipt_status=d.tax_receipt_status or "VERIFIED_80G",
                    tax_receipt_reference=d.tax_receipt_reference,
                )
            )

        return records
    except Exception as e:
        logger.error(f"NGO donations fetch error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.get("/api/ngo/candidates", response_model=List[DonationCandidate])
def get_candidates(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    try:
        candidates = scan_for_near_expiry(db)
        return candidates[offset : offset + limit]
    except Exception as e:
        logger.error(f"NGO candidates scan error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/api/ngo/request", response_model=List[DonationRecord])
def create_donation(request: DonationCreateRequest, db: Session = Depends(get_db)):
    try:
        items_payload = [item.model_dump() for item in request.items]
        donations = create_donation_requests(db, ngo_name=request.ngo_name, items=items_payload)

        records = []
        for d in donations:
            records.append(
                DonationRecord(
                    donation_id=d.donation_id,
                    batch_id=d.batch_id,
                    batch_number=d.batch_number,
                    sku=d.sku,
                    ngo_name=d.ngo_name,
                    product_name=d.product_name,
                    quantity=d.quantity,
                    estimated_value=d.estimated_value,
                    dispatch_timestamp=d.dispatch_timestamp,
                    requested_at=d.requested_at,
                    approved_at=d.approved_at,
                    status=d.status or "PENDING",
                    remaining_seconds_to_approve=120,
                    tax_receipt_status=d.tax_receipt_status or "VERIFIED_80G",
                    tax_receipt_reference=d.tax_receipt_reference,
                )
            )
        return records
    except ValueError as e:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"NGO donation creation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/api/ngo/dispatch/{batch_id}", response_model=DonationRecord)
def dispatch_donation(batch_id: int, request: NgoDispatchRequest, db: Session = Depends(get_db)):
    try:
        record = route_donation(db, batch_id=batch_id, ngo_name=request.ngo_name)
        now = datetime.now(BUSINESS_TIMEZONE)
        req_at = record.requested_at or record.dispatch_timestamp
        if req_at:
            if req_at.tzinfo is None:
                req_at = req_at.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TIMEZONE)
            else:
                req_at = req_at.astimezone(BUSINESS_TIMEZONE)
            elapsed = (now - req_at).total_seconds()
            rem_sec = max(0, int(120 - elapsed))
        else:
            rem_sec = 120

        return DonationRecord(
            donation_id=record.donation_id,
            batch_id=record.batch_id,
            batch_number=record.batch_number,
            sku=record.sku,
            ngo_name=record.ngo_name,
            product_name=record.product_name,
            quantity=record.quantity,
            estimated_value=record.estimated_value,
            dispatch_timestamp=record.dispatch_timestamp,
            requested_at=record.requested_at,
            approved_at=record.approved_at,
            status=record.status or "PENDING",
            remaining_seconds_to_approve=rem_sec,
            tax_receipt_status=record.tax_receipt_status or "VERIFIED_80G",
            tax_receipt_reference=record.tax_receipt_reference,
        )
    except ValueError as e:
        err = str(e)
        if "not found" in err:
            raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=err)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"NGO donation dispatch error: {e}", exc_info=True)
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
