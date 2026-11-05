from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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

    recorded_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )