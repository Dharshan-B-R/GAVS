from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False, index=True)
    proposal_id = Column(Integer, ForeignKey("purchase_proposals.id", ondelete="RESTRICT"), nullable=True, unique=True, index=True)
    status = Column(String(20), nullable=False, default="received", server_default="received")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    invoice_number = Column(String(100), nullable=True, index=True)
    purchase_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expected_delivery_date = Column(Date, nullable=True, index=True)
    received_at = Column(DateTime(timezone=True), nullable=True, index=True)
    total_amount = Column(Float, nullable=False, default=0)
    invoice_amount = Column(Float, nullable=True)
    payment_status = Column(String(30), nullable=False, default="pending")
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier")
    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")
    payments = relationship("PurchasePayment", back_populates="purchase", cascade="all, delete-orphan")
