from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


# Customer Create Schema
# Purpose: Validate customer details when creating a customer.
# Method: POST
# Endpoint: /customers

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


# Customer Update Schema
# Purpose: Validate customer details when updating a customer.
# Method: PUT
# Endpoint: /customers/{customer_id}

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


# Customer Response Schema
# Purpose: Define the customer information returned by the API.
# Method: GET
# Endpoint: /customers

class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)