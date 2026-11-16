"""Separate actual supplier invoice totals from internal purchase-order estimates."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e1b4c6d8a920"
down_revision: Union[str, Sequence[str], None] = "d13b7a9c5e20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchases", sa.Column("invoice_amount", sa.Float(), nullable=True))
    op.add_column("purchases", sa.Column("supplier_invoice_number", sa.String(100), nullable=True))
    op.create_index("ix_purchases_supplier_invoice_number", "purchases", ["supplier_invoice_number"])


def downgrade() -> None:
    op.drop_index("ix_purchases_supplier_invoice_number", table_name="purchases")
    op.drop_column("purchases", "supplier_invoice_number")
    op.drop_column("purchases", "invoice_amount")
