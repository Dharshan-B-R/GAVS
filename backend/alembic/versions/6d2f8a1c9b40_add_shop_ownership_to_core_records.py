"""Assign legacy business records to the sole existing shop and add tenant keys.

This migration is intentionally fail-closed: it refuses to run unless exactly one
shop exists. No ownership is inferred from user IDs or transaction contents.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6d2f8a1c9b40"
down_revision: Union[str, Sequence[str], None] = "4a91c2d7e610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    shop_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM shops ORDER BY id"))]
    if len(shop_ids) != 1:
        raise RuntimeError(
            "Cannot safely backfill tenant ownership: expected exactly one shop, "
            f"found {len(shop_ids)}. Create an explicit ownership mapping before retrying."
        )
    shop_id = shop_ids[0]

    # Add nullable first so existing rows can be assigned without losing data.
    for table in ("products", "sales", "purchases"):
        op.add_column(table, sa.Column("shop_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f'UPDATE "{table}" SET shop_id = :shop_id WHERE shop_id IS NULL').bindparams(shop_id=shop_id))
        op.alter_column(table, "shop_id", existing_type=sa.Integer(), nullable=False)
        op.create_foreign_key(
            f"fk_{table}_shop_id_shops", table, "shops",
            ["shop_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_shop_id", table, ["shop_id"])

    # The old global barcode constraint blocks the same barcode in different
    # shops. Replace it with a tenant-scoped unique constraint.
    op.drop_constraint("products_barcode_key", "products", type_="unique")
    op.create_unique_constraint(
        "uq_products_shop_barcode", "products", ["shop_id", "barcode"]
    )


def downgrade() -> None:
    # Refuse to discard tenant ownership once multiple shops may exist.
    bind = op.get_bind()
    shop_count = bind.execute(sa.text("SELECT COUNT(*) FROM shops")).scalar_one()
    if shop_count != 1:
        raise RuntimeError("Refusing downgrade: multiple shops exist; tenant ownership cannot be discarded safely.")

    op.drop_constraint("uq_products_shop_barcode", "products", type_="unique")
    op.create_unique_constraint("products_barcode_key", "products", ["barcode"])
    for table in ("purchases", "sales", "products"):
        op.drop_index(f"ix_{table}_shop_id", table_name=table)
        op.drop_constraint(f"fk_{table}_shop_id_shops", table, type_="foreignkey")
        op.drop_column(table, "shop_id")
