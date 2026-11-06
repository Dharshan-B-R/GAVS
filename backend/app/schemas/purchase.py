
# ---------------------------------------------------------
# SCHEMAS: Purchase Management
# Purpose:
# Validates supplier purchase invoices and their products.
# Captures batch number, manufacturing date and expiry date.
# ---------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# Individual product in a purchase
class PurchaseItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)

    batch_number: str = Field(..., min_length=1, max_length=100)
    manufacturing_date: Optional[date] = None
    expiry_date: date


# Complete purchase request
class PurchaseCreate(BaseModel):
    supplier_id: int = Field(..., gt=0)
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)

    items: List[PurchaseItemCreate] = Field(..., min_length=1)


# Purchase item response
class PurchaseItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True




# ---------------------------------------------------------
# SCHEMAS: Purchase Management
# Purpose:
# Validates supplier purchase requests and responses.
# Supports multiple products and batch information.
# ---------------------------------------------------------

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# Individual product in a purchase request
class PurchaseItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)

    batch_number: str = Field(..., min_length=1, max_length=100)
    manufacturing_date: Optional[date] = None
    expiry_date: date


# Complete purchase request
class PurchaseCreate(BaseModel):
    supplier_id: int = Field(..., gt=0)
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)

    items: List[PurchaseItemCreate] = Field(..., min_length=1)


# Individual purchase item response
# Individual purchase item response
class PurchaseItemResponse(BaseModel):
    id: int
    product_id: int
    batch_id: Optional[int] = None
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True

# Complete purchase response
class PurchaseResponse(BaseModel):
    id: int
    supplier_id: int
    invoice_number: Optional[str]
    purchase_date: datetime
    total_amount: float
    payment_status: str
    notes: Optional[str]

    items: List[PurchaseItemResponse] = []

    class Config:
        from_attributes = True
