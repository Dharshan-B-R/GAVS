from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal


# ============================================================
# KHATA TRANSACTION CREATE SCHEMA
# Purpose: Validate customer credit and repayment requests.
# Method: POST
# Endpoint: /customers/{customer_id}/khata
# ============================================================

class KhataTransactionCreate(BaseModel):
    transaction_type: Literal["credit", "repayment"]

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    description: Optional[str] = None

    reference_number: Optional[str] = None


# ============================================================
# KHATA TRANSACTION RESPONSE SCHEMA
# Purpose: Define the transaction details returned by the API.
# ============================================================

class KhataTransactionResponse(BaseModel):
    id: int
    customer_id: int
    transaction_type: str
    amount: Decimal
    description: Optional[str] = None
    reference_number: Optional[str] = None
    performed_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)