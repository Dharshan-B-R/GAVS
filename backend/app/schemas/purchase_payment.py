
# ---------------------------------------------------------
# SCHEMAS: Purchase Payment Management
# Purpose:
# Validates full and partial supplier payment requests.
# Supports Cash, UPI and Bank Transfer payments.
# ---------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# Supported payment methods
class PaymentMethod(str, Enum):
    CASH = "cash"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"


# Create purchase payment request
class PurchasePaymentCreate(BaseModel):
    amount: float = Field(..., gt=0)

    payment_method: PaymentMethod

    transaction_reference: Optional[str] = Field(
        default=None,
        max_length=150
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=500
    )


# Purchase payment response
class PurchasePaymentResponse(BaseModel):
    id: int
    purchase_id: int
    amount: float
    payment_method: str
    transaction_reference: Optional[str]
    notes: Optional[str]
    paid_at: datetime

    class Config:
        from_attributes = True
