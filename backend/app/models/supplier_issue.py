"""Supplier issue and dispute evidence owned by a shop."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class SupplierIssue(Base):
    __tablename__ = "supplier_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_supplier_issue_severity"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_supplier_issue_status"),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True, index=True)
    issue_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="medium", server_default="medium")
    status = Column(String(20), nullable=False, default="open", server_default="open")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
