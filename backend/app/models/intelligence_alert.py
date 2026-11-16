"""Deduplicated shop-scoped actionable intelligence alerts."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class IntelligenceAlert(Base):
    __tablename__ = "intelligence_alerts"
    __table_args__ = (
        UniqueConstraint("shop_id", "dedupe_key", name="uq_intelligence_alert_shop_dedupe"),
        CheckConstraint("severity IN ('info', 'warning', 'high', 'critical')", name="ck_intelligence_alert_severity"),
        CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_intelligence_alert_status"),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_type = Column(String(50), nullable=False)
    dedupe_key = Column(String(180), nullable=False)
    severity = Column(String(20), nullable=False, default="warning", server_default="warning")
    title = Column(String(180), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="open", server_default="open")
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
