
# ==========================================
# KIRANA AI - SHOP DISTRIBUTOR CONNECTION MODEL
#
# Purpose:
# 1. Connect shops with distributors.
# 2. Support one distributor serving multiple shops.
# 3. Support multiple distributors serving one shop.
# 4. Prevent duplicate shop-distributor connections.
# 5. Track connection activation status.
#
# Database table: shop_distributor_connections
# ==========================================

from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)

from sqlalchemy.sql import func, text

from app.database import Base


class ShopDistributorConnection(Base):
    __tablename__ = "shop_distributor_connections"

    # Prevent duplicate connections between the same shop and distributor.
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "supplier_id",
            name="uq_shop_distributor_connection",
        ),
    )

    # Unique connection identifier.
    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # Shop associated with this distributor.
    shop_id = Column(
        Integer,
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Existing distributor business record.
    # RESTRICT prevents deleting a supplier while connections exist.
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Indicates whether the connection is active.
    is_active = Column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    # Records when the connection is created.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Records the latest connection update.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
