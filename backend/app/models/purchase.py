
# ---------------------------------------------------------
# MODEL: Purchase
# Purpose:
# Stores supplier purchase transactions and invoice details.
# Maintains relationships with supplier and purchase items.
# ---------------------------------------------------------

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)

    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=False,
        index=True
    )

    invoice_number = Column(String(100), nullable=True, index=True)

    purchase_date = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    total_amount = Column(Float, nullable=False, default=0)

    payment_status = Column(
        String(30),
        nullable=False,
        default="pending"
    )

    notes = Column(String(500), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    supplier = relationship("Supplier")

    items = relationship(
        "PurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan"
    )
