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


def downgrade() -> None:
    op.drop_column("purchases", "invoice_amount")
