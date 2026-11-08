
# ---------------------------------------------------------
# MODEL: SaleItem
# Purpose:
# Stores individual products included in a sales transaction.
# Preserves the actual selling price and stock movement reference
# for accurate historical sales analytics.
# ---------------------------------------------------------

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    ForeignKey
)
from sqlalchemy.orm import relationship

from app.database import Base


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(
        Integer,
        ForeignKey("sales.id"),
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    stock_movement_id = Column(
        Integer,
        ForeignKey("stock_movements.id"),
        nullable=True,
        unique=True,
        index=True
    )

    # Preserve product details at the time of sale
    product_name = Column(String(150), nullable=False)

    unit = Column(String(30), nullable=False)

    quantity = Column(Float, nullable=False)

    # Actual price charged at the time of sale
    unit_price = Column(Float, nullable=False)

    discount_amount = Column(Float, nullable=False, default=0)

    subtotal = Column(Float, nullable=False)

    # Relationships
    sale = relationship(
        "Sale",
        back_populates="items"
    )

    product = relationship("Product")

    stock_movement = relationship("StockMovement")
