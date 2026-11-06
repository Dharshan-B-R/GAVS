
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


class BatchVerification(Base):
    __tablename__ = "batch_verifications"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("product_batches.id"),
        nullable=False
    )

    previous_quantity = Column(Float, nullable=False)
    verified_quantity = Column(Float, nullable=False)

    performed_by = Column(Integer, nullable=True)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    reason = Column(String(255), nullable=True)

    allow_reverification = Column(
        Integer,
        nullable=False,
        default=0
    )

    verified_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
