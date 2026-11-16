"""Add shop-owned khata, supplier receipt evidence and local demand context.

Legacy customers remain unassigned (shop_id NULL); no customer balance is attributed
to a shop without an explicit owner action. Existing received purchase quantities
are backfilled as both ordered and received quantities because older records contain
only one quantity and were already marked received.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c42e8a7d1f30"
down_revision: Union[str, Sequence[str], None] = "b31f6a9d2c10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("shop_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_customers_shop_id_shops", "customers", "shops",
        ["shop_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_customers_shop_id", "customers", ["shop_id"])

    op.add_column("shops", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("shops", sa.Column("state", sa.String(100), nullable=True))
    op.add_column("shops", sa.Column("country", sa.String(100), nullable=False, server_default="India"))
    op.add_column("shops", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"))

    op.add_column("purchases", sa.Column("expected_delivery_date", sa.Date(), nullable=True))
    op.add_column("purchases", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_purchases_expected_delivery_date", "purchases", ["expected_delivery_date"])
    op.create_index("ix_purchases_received_at", "purchases", ["received_at"])

    op.add_column("purchase_items", sa.Column("ordered_quantity", sa.Float(), nullable=True))
    op.add_column("purchase_items", sa.Column("received_quantity", sa.Float(), nullable=False, server_default="0"))
    op.execute(sa.text("""
        UPDATE purchase_items
        SET ordered_quantity = quantity,
            received_quantity = CASE
                WHEN purchases.status = 'received' THEN quantity
                ELSE 0
            END
        FROM purchases
        WHERE purchases.id = purchase_items.purchase_id
    """))

    op.create_table(
        "festival_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False, server_default="festival"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "event_date", "name", name="uq_festival_event_shop_date_name"),
    )
    op.create_index("ix_festival_events_shop_id", "festival_events", ["shop_id"])
    op.create_index("ix_festival_events_event_date", "festival_events", ["event_date"])

    op.create_table(
        "inventory_availability_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("available_quantity", sa.Float(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("captured_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "product_id", "snapshot_date", name="uq_inventory_availability_shop_product_day"),
    )
    op.create_index("ix_inventory_availability_snapshots_shop_id", "inventory_availability_snapshots", ["shop_id"])
    op.create_index("ix_inventory_availability_snapshots_product_id", "inventory_availability_snapshots", ["product_id"])
    op.create_index("ix_inventory_availability_snapshots_snapshot_date", "inventory_availability_snapshots", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_inventory_availability_snapshots_snapshot_date", table_name="inventory_availability_snapshots")
    op.drop_index("ix_inventory_availability_snapshots_product_id", table_name="inventory_availability_snapshots")
    op.drop_index("ix_inventory_availability_snapshots_shop_id", table_name="inventory_availability_snapshots")
    op.drop_table("inventory_availability_snapshots")

    op.drop_index("ix_festival_events_event_date", table_name="festival_events")
    op.drop_index("ix_festival_events_shop_id", table_name="festival_events")
    op.drop_table("festival_events")

    op.drop_column("purchase_items", "received_quantity")
    op.drop_column("purchase_items", "ordered_quantity")
    op.drop_index("ix_purchases_received_at", table_name="purchases")
    op.drop_index("ix_purchases_expected_delivery_date", table_name="purchases")
    op.drop_column("purchases", "received_at")
    op.drop_column("purchases", "expected_delivery_date")

    op.drop_column("shops", "timezone")
    op.drop_column("shops", "country")
    op.drop_column("shops", "state")
    op.drop_column("shops", "city")

    op.drop_index("ix_customers_shop_id", table_name="customers")
    op.drop_constraint("fk_customers_shop_id_shops", "customers", type_="foreignkey")
    op.drop_column("customers", "shop_id")
