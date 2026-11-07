from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base


# Customer Model
# Purpose: Store customer details for the KiranaAI Khata system.
# Used for: Customer credit records, repayments and outstanding balances.

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False, index=True)

    phone = Column(String(15), nullable=True, index=True)

    address = Column(String(300), nullable=True)

    notes = Column(String(500), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )