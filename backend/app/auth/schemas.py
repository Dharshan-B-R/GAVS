
# ==========================================
# KIRANA AI - AUTHENTICATION SCHEMAS
#
# Purpose:
# 1. Validate user registration details.
# 2. Validate distributor registration details.
# 3. Validate login credentials.
# 4. Define authentication response formats.
# ==========================================

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ==========================================
# SHOP OWNER REGISTRATION SCHEMA
# Purpose:
# Validate details required to create an owner account.
# ==========================================

class OwnerRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    shop_name: str = Field(min_length=2, max_length=150)
    shop_address: Optional[str] = Field(default=None, max_length=300)
    shop_phone: Optional[str] = Field(default=None, max_length=20)
    shop_email: Optional[EmailStr] = None
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)


# ==========================================
# DISTRIBUTOR REGISTRATION SCHEMA
# Purpose:
# Validate distributor account and business details.
# ==========================================

class DistributorRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    business_name: str = Field(min_length=2, max_length=150)
    contact_person: Optional[str] = Field(default=None, max_length=150)
    address: Optional[str] = None
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)


# ==========================================
# LOGIN SCHEMA
# Purpose:
# Validate user login credentials.
# ==========================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


# ==========================================
# AUTHENTICATION RESPONSE SCHEMA
# Purpose:
# Return access token and authentication type.
# ==========================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ==========================================
# USER RESPONSE SCHEMA
# Purpose:
# Return safe authenticated user information.
# ==========================================

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    supplier_id: Optional[int] = None
    is_active: bool
