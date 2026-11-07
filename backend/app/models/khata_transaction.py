from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    CheckConstraint
)
from sqlalchemy.sql import func

from app.database import Base


# ============================================================
# KHATA TRANSACTION MODEL
# Purpose: Store customer credit (Udhar) and repayment records.
# Transaction types: credit and repayment.
# Database table: khata_transactions
# ============================================================

class KhataTransaction(Base):
    __tablename__ = "khata_transactions"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="check_khata_amount_positive"
        ),
        CheckConstraint(
            "transaction_type IN ('credit', 'repayment')",
            name="check_khata_transaction_type"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False,
        index=True
    )

    transaction_type = Column(
        String(20),
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False
    )

    description = Column(
        String(300),
        nullable=True
    )

    reference_number = Column(
        String(100),
        nullable=True
    )

    performed_by = Column(
        String(100),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )