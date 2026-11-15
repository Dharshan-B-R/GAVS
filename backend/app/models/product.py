from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)\n    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False, index=True)\n

    name = Column(String(150), nullable=False, index=True)
    category = Column(String(100), nullable=True)
    barcode = Column(String(100), nullable=True)

    quantity = Column(Float, default=0, nullable=False)
    minimum_stock = Column(Float, default=0, nullable=False)

    purchase_price = Column(Float, default=0, nullable=False)
    selling_price = Column(Float, default=0, nullable=False)

    unit = Column(String(30), default="pieces", nullable=False)

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