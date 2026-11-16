"""Daily deterministic intelligence snapshot for a shop."""
from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.sql import func
from app.database import Base


class IntelligenceDailySummary(Base):
    __tablename__ = "intelligence_daily_summaries"
    __table_args__ = (UniqueConstraint("shop_id", "summary_date", name="uq_intelligence_daily_summary_shop_date"),)

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_date = Column(Date, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
