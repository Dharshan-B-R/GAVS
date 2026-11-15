# ---------------------------------------------------------
# MODEL: Sale
# Purpose:
# Stores completed sales transactions made by the Kirana shop.
# Maintains the relationship with individual sale items.
# ---------------------------------------------------------

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False, index=True)

    total_amount = Column(Float, nullable=False, default=0)
    discount_amount = Column(Float, nullable=False, default=0)
    payment_method = Column(String(30), nullable=True)
    notes = Column(String(500), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    items = relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan"
    )
