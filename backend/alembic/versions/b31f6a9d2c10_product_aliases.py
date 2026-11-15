"""Create shop-scoped product aliases."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b31f6a9d2c10"
down_revision: Union[str, Sequence[str], None] = "8a71c4e2d903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(length=180), nullable=False),
        sa.Column("normalized_alias", sa.String(length=180), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "normalized_alias", name="uq_product_alias_shop_normalized"),
    )
    op.create_index("ix_product_aliases_shop_id", "product_aliases", ["shop_id"])
    op.create_index("ix_product_aliases_product_id", "product_aliases", ["product_id"])
    op.create_index("ix_product_alias_shop_product", "product_aliases", ["shop_id", "product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_alias_shop_product", table_name="product_aliases")
    op.drop_index("ix_product_aliases_product_id", table_name="product_aliases")
    op.drop_index("ix_product_aliases_shop_id", table_name="product_aliases")
    op.drop_table("product_aliases")
