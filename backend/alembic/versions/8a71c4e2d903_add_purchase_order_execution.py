"""Add internal purchase-order execution records for approved proposals."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "8a71c4e2d903"
down_revision: Union[str, Sequence[str], None] = "6d2f8a1c9b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchases", sa.Column("proposal_id", sa.Integer(), nullable=True))
    op.add_column("purchases", sa.Column("status", sa.String(20), nullable=False, server_default="received"))
    op.create_foreign_key(
        "fk_purchases_proposal_id_purchase_proposals", "purchases",
        "purchase_proposals", ["proposal_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_purchases_proposal_id", "purchases", ["proposal_id"])
    op.create_index("ix_purchases_proposal_id", "purchases", ["proposal_id"])
    # Measured grocery items commonly use fractional quantities (kg/litres).
    op.alter_column(
        "purchase_items", "quantity",
        existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False,
        postgresql_using="quantity::double precision",
    )


def downgrade() -> None:
    # Do not silently truncate fractional quantities during rollback.
    bind = op.get_bind()
    fractional = bind.execute(sa.text(
        "SELECT COUNT(*) FROM purchase_items WHERE quantity <> FLOOR(quantity)"
    )).scalar_one()
    if fractional:
        raise RuntimeError("Cannot downgrade purchase quantity type: fractional quantities exist.")
    op.alter_column(
        "purchase_items", "quantity",
        existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False,
        postgresql_using="quantity::integer",
    )
    op.drop_index("ix_purchases_proposal_id", table_name="purchases")
    op.drop_constraint("uq_purchases_proposal_id", "purchases", type_="unique")
    op.drop_constraint("fk_purchases_proposal_id_purchase_proposals", "purchases", type_="foreignkey")
    op.drop_column("purchases", "status")
    op.drop_column("purchases", "proposal_id")
