
# ---------------------------------------------------------
# MODEL: PurchaseItem
# Purpose:
# Stores individual products included in a supplier purchase.
# Links each purchase item to its corresponding inventory batch.
# ---------------------------------------------------------

from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id"),
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    batch_id = Column(
        Integer,
        ForeignKey("product_batches.id"),
        nullable=True,
        unique=True,
        index=True
    )

    quantity = Column(Integer, nullable=False)

    unit_price = Column(Float, nullable=False)

    subtotal = Column(Float, nullable=False)

    purchase = relationship(
    "Purchase",
    back_populates="items"
)
    
    product = relationship("Product")
    batch = relationship("ProductBatch")
