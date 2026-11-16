
# ==========================================
# KIRANA AI - SHOP MEMBERSHIP MODEL
# Purpose:
# 1. Connect users with their shops.
# 2. Support owners managing multiple shops.
# 3. Support multiple employees in each shop.
# 4. Store membership roles and permissions.
#
# Database table: shop_memberships
# ==========================================

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class ShopMembership(Base):
    __tablename__ = "shop_memberships"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "shop_id",
            name="uq_shop_membership_user_shop",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shop_id = Column(
        Integer,
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role = Column(String(20), nullable=False)
    job_role = Column(String(30), nullable=False, default="manager", server_default="manager")

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
