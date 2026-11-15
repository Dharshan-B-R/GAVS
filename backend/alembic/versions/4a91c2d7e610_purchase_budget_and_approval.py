"""Add per-shop purchase budgets and owner approval proposals."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "4a91c2d7e610"
down_revision: Union[str, Sequence[str], None] = "3b760ed11415"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_purchase_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("available_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("available_amount >= 0", name="ck_shop_purchase_budget_nonnegative"),
        sa.UniqueConstraint("shop_id", name="uq_shop_purchase_budgets_shop_id"),
    )
    op.create_index("ix_shop_purchase_budgets_shop_id", "shop_purchase_budgets", ["shop_id"])

    op.create_table(
        "purchase_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("budget_at_creation", sa.Numeric(14, 2), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.String(1000), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("total_amount >= 0", name="ck_purchase_proposal_total_nonnegative"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled', 'ordered')", name="ck_purchase_proposal_status"),
    )
    op.create_index("ix_purchase_proposals_shop_id", "purchase_proposals", ["shop_id"])
    op.create_index("ix_purchase_proposals_supplier_id", "purchase_proposals", ["supplier_id"])
    op.create_index("ix_purchase_proposals_status", "purchase_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("purchase_proposals")
    op.drop_table("shop_purchase_budgets")
