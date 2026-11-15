"""Shop-scoped alternative names for products.

Aliases improve matching of local names, spelling variants and distributor labels
without changing or merging canonical product records.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func

from app.database import Base


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint("shop_id", "normalized_alias", name="uq_product_alias_shop_normalized"),
        Index("ix_product_alias_shop_product", "shop_id", "product_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(180), nullable=False)
    normalized_alias = Column(String(180), nullable=False)
    source = Column(String(30), nullable=False, default="owner")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
