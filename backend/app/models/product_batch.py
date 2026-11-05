from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Boolean
)
from sqlalchemy.sql import func

from app.database import Base


class ProductBatch(Base):
    __tablename__ = "product_batches"

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    batch_number = Column(
        String(100),
        nullable=False
    )

    manufacturing_date = Column(Date, nullable=True)

    expiry_date = Column(Date, nullable=False)

    quantity = Column(Float, default=0, nullable=False)

    purchase_price = Column(Float, default=0, nullable=False)

    # Batch verification status
    is_verified = Column(
        Boolean,
        default=False,
        nullable=False
    )

    verified_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )