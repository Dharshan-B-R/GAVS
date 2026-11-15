"""Per-shop cash budget controlled by the shop owner."""
from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class ShopPurchaseBudget(Base):
    __tablename__ = "shop_purchase_budgets"
    __table_args__ = (
        CheckConstraint("available_amount >= 0", name="ck_shop_purchase_budget_nonnegative"),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    available_amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(Integer, nullable=False, default=356)  # ISO 4217 numeric code: INR
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
