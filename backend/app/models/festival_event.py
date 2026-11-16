"""Shop-configured local festival and event calendar."""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class FestivalEvent(Base):
    __tablename__ = "festival_events"
    __table_args__ = (UniqueConstraint("shop_id", "event_date", "name", name="uq_festival_event_shop_date_name"),)

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    event_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(40), nullable=False, default="festival", server_default="festival")
    notes = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
