
# ==========================================
# SHOP DATABASE MODEL
# Purpose:
# 1. Store Kirana shop information.
# 2. Support multiple shops under one owner.
# 3. Maintain shop contact and business details.
# 4. Track shop activation status.
#
# Database table: shops
# ==========================================

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime
)
from sqlalchemy.sql import func

from app.database import Base


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False)

    address = Column(String(300), nullable=True)

    phone = Column(String(20), nullable=True)

    email = Column(String(150), nullable=True)

    gstin = Column(String(20), nullable=True, unique=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
