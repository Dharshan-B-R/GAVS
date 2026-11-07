
# ---------------------------------------------------------
# MODEL: PurchasePayment
# Purpose:
# Records full and partial payments made against supplier
# purchase invoices. Maintains individual payment history.
# ---------------------------------------------------------

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PurchasePayment(Base):
    __tablename__ = "purchase_payments"

    id = Column(Integer, primary_key=True, index=True)

    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id"),
        nullable=False,
        index=True
    )

    amount = Column(Float, nullable=False)

    payment_method = Column(
        String(30),
        nullable=False
    )

    transaction_reference = Column(
        String(150),
        nullable=True
    )

    notes = Column(String(500), nullable=True)

    paid_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    purchase = relationship(
        "Purchase",
        back_populates="payments"
    )
