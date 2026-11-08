
# ---------------------------------------------------------
# SCHEMAS: Sales Management
# Purpose:
# Validates multi-product sales transactions.
# Supports decimal quantities, item discounts and bill discounts.
# Selling prices will be obtained from the backend Product records.
# ---------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.schemas.purchase_payment import PaymentMethod


# Individual product in a customer bill
class SaleItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)

    quantity: float = Field(..., gt=0)

    discount_amount: float = Field(default=0, ge=0)


# Complete customer sales request
class SaleCreate(BaseModel):
    items: List[SaleItemCreate] = Field(..., min_length=1)

    discount_amount: float = Field(default=0, ge=0)

    payment_method: PaymentMethod

    notes: Optional[str] = Field(default=None, max_length=500)


# Individual product in the sales response
class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    stock_movement_id: Optional[int]
    product_name: str
    unit: str
    quantity: float
    unit_price: float
    discount_amount: float
    subtotal: float

    class Config:
        from_attributes = True


# Complete sales transaction response
class SaleResponse(BaseModel):
    id: int
    total_amount: float
    discount_amount: float
    payment_method: Optional[str]
    notes: Optional[str]
    created_at: datetime

    items: List[SaleItemResponse] = []

    class Config:
        from_attributes = True
