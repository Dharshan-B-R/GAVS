"""Owner/staff feedback on AI purchase recommendations."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        CheckConstraint("decision IN ('accepted', 'dismissed', 'adjusted')", name="ck_recommendation_feedback_decision"),
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    recommendation_type = Column(String(50), nullable=False, default="reorder", server_default="reorder")
    recommendation_key = Column(String(180), nullable=False)
    decision = Column(String(20), nullable=False)
    recommended_quantity = Column(Float, nullable=True)
    actual_quantity = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
