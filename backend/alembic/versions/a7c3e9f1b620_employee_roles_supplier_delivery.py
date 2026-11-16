"""Add employee job profiles and supplier order progress fields."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a7c3e9f1b620"
down_revision: Union[str, Sequence[str], None] = "f2a9c7d1e530"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shop_memberships", sa.Column("job_role", sa.String(30), nullable=False, server_default="manager"))
    op.create_check_constraint(
        "ck_shop_membership_job_role", "shop_memberships",
        "job_role IN ('manager', 'cashier', 'stock_manager')",
    )
    op.add_column("purchases", sa.Column("supplier_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("purchases", sa.Column("supplier_status_note", sa.String(500), nullable=True))
    op.add_column("purchases", sa.Column("supplier_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_purchase_supplier_status", "purchases",
        "supplier_status IN ('pending', 'preparing', 'dispatched', 'delayed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_purchase_supplier_status", "purchases", type_="check")
    op.drop_column("purchases", "supplier_updated_at")
    op.drop_column("purchases", "supplier_status_note")
    op.drop_column("purchases", "supplier_status")
    op.drop_constraint("ck_shop_membership_job_role", "shop_memberships", type_="check")
    op.drop_column("shop_memberships", "job_role")
