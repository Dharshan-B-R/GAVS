"""Daily point-in-time product availability observations for demand censoring."""
from sqlalchemy import Column, Integer, Float, Boolean, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class InventoryAvailabilitySnapshot(Base):
    __tablename__ = "inventory_availability_snapshots"
    __table_args__ = (UniqueConstraint("shop_id", "product_id", "snapshot_date", name="uq_inventory_availability_shop_product_day"),)

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    available_quantity = Column(Float, nullable=False)
    is_available = Column(Boolean, nullable=False)
    captured_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
