"""Auditable, owner-approved purchase proposals. Does not place orders."""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, CheckConstraint, JSON
from sqlalchemy.sql import func
from app.database import Base


class PurchaseProposal(Base):
    __tablename__ = "purchase_proposals"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_purchase_proposal_total_nonnegative"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled', 'ordered')", name="ck_purchase_proposal_status"),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    total_amount = Column(Numeric(14, 2), nullable=False)
    budget_at_creation = Column(Numeric(14, 2), nullable=False)
    items = Column(JSON, nullable=False)
    rationale = Column(String(1000), nullable=True)
    decision_note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
