from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BatchResponse(BaseModel):
    id: int
    product_id: int
    batch_number: Optional[str] = None
    internal_batch_id: str
    manufacturing_date: Optional[str] = None
    expiry_date: str
    stock_quantity: int
    current_discount: float
    daily_demand: int
    status: str
    remaining_hours: Optional[float] = None
    remaining_days: Optional[float] = None
    remaining_text: Optional[str] = None
    dynamic_discount_percent: float = 0.0
    dynamic_discount_fraction: float = 0.0
    final_price: float = 0.0
    is_override: bool = False
    override_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    id: int
    sku: str
    product_name: str
    category: str
    manufacturer: Optional[str] = None
    base_price: float
    mrp: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    batches: List[BatchResponse] = []

    class Config:
        from_attributes = True


class InventoryItemResponse(BaseModel):
    sku: str
    product_name: str
    category: str
    manufacturer: Optional[str] = None
    base_price: float
    mrp: Optional[float] = None
    batch_number: Optional[str] = None
    internal_batch_id: str
    manufacturing_date: Optional[str] = None
    expiry_date: str
    stock_quantity: int
    current_discount: float
    daily_demand: int
    status: str
    remaining_hours: Optional[float] = None
    remaining_days: Optional[float] = None
    remaining_text: Optional[str] = None
    dynamic_discount_percent: float = 0.0
    dynamic_discount_fraction: float = 0.0
    final_price: float = 0.0
    is_override: bool = False
    override_reason: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class InventoryListResponse(BaseModel):
    items: List[InventoryItemResponse]
    total: int
    limit: int
    offset: int


class ExistingBatchInfo(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    batch_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: str
    stock_quantity: int


class BatchCreateRequest(BaseModel):
    product_name: str = Field(..., min_length=1)
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    batch_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: str
    base_price: Optional[float] = None
    mrp: Optional[float] = None
    stock_quantity: int = Field(..., gt=0)
    confirm_existing: bool = False
    force_new_batch: bool = False


class PricingRequest(BaseModel):
    remaining_hours: float = Field(..., description="Hours until product expires")
    base_price: float = Field(..., gt=0.0, description="Base price of the product")
    initial_quantity: int = Field(..., gt=0, description="Initial stock quantity")
    daily_demand: int = Field(..., ge=0, description="Expected daily demand")


class PricingResponse(BaseModel):
    recommended_discount: float = Field(
        ..., ge=0.0, le=0.70, description="Recommended discount fraction (0.00 to 0.70)"
    )
    dynamic_discount_percent: Optional[float] = None
    final_price: Optional[float] = None
    is_override: Optional[bool] = False
    override_reason: Optional[str] = None


class TaxRequest(BaseModel):
    taxable_amount: Decimal = Field(..., ge=0, description="Amount subject to tax")
    tax_rate: Decimal = Field(..., ge=0, description="Explicit tax rate (e.g., 0.05 for 5%)")


class TaxResponse(BaseModel):
    tax_collected: Decimal
    final_amount: Decimal


class TaxLedgerInsertRequest(BaseModel):
    transaction_id: str = Field(..., min_length=1)
    taxable_amount: Decimal = Field(..., ge=0)
    tax_rate: Decimal = Field(..., ge=0)


class TaxLedgerResponse(BaseModel):
    transaction_id: str
    total_sale_amount_cents: int
    tax_collected_cents: int
    timestamp: datetime
    record_hash: str

    class Config:
        from_attributes = True


class DonationCandidate(BaseModel):
    batch_id: int
    sku: str
    batch_number: Optional[str] = None
    product_name: str
    category: str
    manufacturer: Optional[str] = None
    stock_quantity: int
    base_price: float
    mrp: Optional[float] = None
    expiry_date: str
    remaining_hours: float
    remaining_days: Optional[float] = None
    remaining_text: Optional[str] = None
    daily_demand: int
    estimated_value: Decimal
    status: str = "DONATION"


class DonationItemRequest(BaseModel):
    batch_id: int
    quantity: int = Field(..., gt=0)


class DonationCreateRequest(BaseModel):
    ngo_name: str = Field(..., min_length=1)
    items: List[DonationItemRequest] = Field(..., min_items=1)


class DonationRecord(BaseModel):
    donation_id: int
    batch_id: int
    batch_number: Optional[str] = None
    sku: str
    ngo_name: str
    product_name: str
    quantity: int
    estimated_value: float
    dispatch_timestamp: datetime
    requested_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    status: str = "PENDING"
    remaining_seconds_to_approve: int = 0
    tax_receipt_status: str
    tax_receipt_reference: str

    class Config:
        from_attributes = True


class NgoDispatchRequest(BaseModel):
    ngo_name: str = Field(..., min_length=1, description="Configured NGO partner name")


class DashboardStatsResponse(BaseModel):
    total_inventory_items: int
    safe_count: int
    near_expiry_count: int
    critical_count: int
    donation_count: int
    expired_count: int
    ngo_candidates: int
    donation_units_count: int


class FieldExtraction(BaseModel):
    value: Optional[Any] = None
    confidence: float = 0.0
    source: str = "semantic"


class OcrExtractionResult(BaseModel):
    success: bool = True
    product_name: Optional[str] = None
    manufacturer: Optional[str] = None
    sku: Optional[str] = None
    batch_number: Optional[str] = None
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    mrp: Optional[float] = None
    base_price: Optional[float] = None
    category: Optional[str] = None

    semantic_fields: Dict[str, FieldExtraction] = {}
    confidence: Dict[str, float] = {}
    raw_text: str = ""
    warnings: List[str] = []
    conflicts: List[str] = []
