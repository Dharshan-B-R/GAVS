"""Add shop-scoped supplier issue and dispute tracking."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d13b7a9c5e20"
down_revision: Union[str, Sequence[str], None] = "c42e8a7d1f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issue_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_supplier_issue_severity"),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_supplier_issue_status"),
    )
    op.create_index("ix_supplier_issues_shop_id", "supplier_issues", ["shop_id"])
    op.create_index("ix_supplier_issues_supplier_id", "supplier_issues", ["supplier_id"])
    op.create_index("ix_supplier_issues_purchase_id", "supplier_issues", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_issues_purchase_id", table_name="supplier_issues")
    op.drop_index("ix_supplier_issues_supplier_id", table_name="supplier_issues")
    op.drop_index("ix_supplier_issues_shop_id", table_name="supplier_issues")
    op.drop_table("supplier_issues")
