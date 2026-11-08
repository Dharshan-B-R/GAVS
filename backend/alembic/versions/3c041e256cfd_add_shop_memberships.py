
"""
KiranaAI shop membership migration.

Creates only the shop_memberships table.
Preserves all existing tables and indexes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Migration revision identifiers.
revision: str = "3c041e256cfd"
down_revision: Union[str, Sequence[str], None] = "05dda7befb90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================
# UPGRADE
# Purpose:
# Create shop membership relationships.
# ==========================================

def upgrade() -> None:

    op.create_table(
        "shop_memberships",

        sa.Column("id", sa.Integer(), nullable=False),

        sa.Column("user_id", sa.Integer(), nullable=False),

        sa.Column("shop_id", sa.Integer(), nullable=False),

        sa.Column("role", sa.String(length=20), nullable=False),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "user_id",
            "shop_id",
            name="uq_shop_membership_user_shop",
        ),
    )

    op.create_index(
        "ix_shop_memberships_id",
        "shop_memberships",
        ["id"],
    )

    op.create_index(
        "ix_shop_memberships_user_id",
        "shop_memberships",
        ["user_id"],
    )

    op.create_index(
        "ix_shop_memberships_shop_id",
        "shop_memberships",
        ["shop_id"],
    )


# ==========================================
# DOWNGRADE
# Purpose:
# Remove only the membership table.
# ==========================================

def downgrade() -> None:

    op.drop_index(
        "ix_shop_memberships_shop_id",
        table_name="shop_memberships",
    )

    op.drop_index(
        "ix_shop_memberships_user_id",
        table_name="shop_memberships",
    )

    op.drop_index(
        "ix_shop_memberships_id",
        table_name="shop_memberships",
    )

    op.drop_table("shop_memberships")
