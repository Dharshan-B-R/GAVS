
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey
)
from sqlalchemy.sql import func

from app.database import Base


class ExpiryRecord(Base):
    __tablename__ = "expiry_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("product_batches.id"),
        nullable=False
    )

    quantity = Column(Float, nullable=False)

    action = Column(
        String(50),
        nullable=False
    )

    reason = Column(String(255), nullable=True)

    # Supplier relationship
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=True,
        index=True
    )

    # Supplier return workflow
    supplier_name = Column(
        String(150),
        nullable=True
    )

    return_status = Column(
        String(30),
        nullable=False,
        default="not_applicable"
    )

    supplier_reference = Column(
        String(100),
        nullable=True
    )

    approved_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    picked_up_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    credit_amount = Column(
        Float,
        nullable=True
    )

    credited_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    recorded_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
