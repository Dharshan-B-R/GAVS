from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    category: Optional[str] = None
    barcode: Optional[str] = None

    quantity: float = Field(default=0, ge=0)
    minimum_stock: float = Field(default=0, ge=0)

    purchase_price: float = Field(default=0, ge=0)
    selling_price: float = Field(default=0, ge=0)

    unit: str = "pieces"


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    category: Optional[str] = None
    barcode: Optional[str] = None

    quantity: Optional[float] = Field(default=None, ge=0)
    minimum_stock: Optional[float] = Field(default=None, ge=0)

    purchase_price: Optional[float] = Field(default=None, ge=0)
    selling_price: Optional[float] = Field(default=None, ge=0)

    unit: Optional[str] = None
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str]
    barcode: Optional[str]
    quantity: float
    minimum_stock: float
    purchase_price: float
    selling_price: float
    unit: str
    is_active: bool