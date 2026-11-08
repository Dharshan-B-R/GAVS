
"""
KiranaAI distributor connections and invitations migration.

Creates only:
1. shop_distributor_connections
2. shop_invitations

Preserves all existing business tables and indexes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Migration revision identifiers.
revision: str = "3b760ed11415"
down_revision: Union[str, Sequence[str], None] = "3c041e256cfd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================
# UPGRADE
# Purpose:
# Create distributor connections and invitations.
# ==========================================

def upgrade() -> None:

    # Create shop-distributor connections.
    op.create_table(
        "shop_distributor_connections",

        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),

        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
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
            ["shop_id"],
            ["shops.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "shop_id",
            "supplier_id",
            name="uq_shop_distributor_connection",
        ),
    )

    op.create_index(
        "ix_shop_distributor_connections_id",
        "shop_distributor_connections",
        ["id"],
    )

    op.create_index(
        "ix_shop_distributor_connections_shop_id",
        "shop_distributor_connections",
        ["shop_id"],
    )

    op.create_index(
        "ix_shop_distributor_connections_supplier_id",
        "shop_distributor_connections",
        ["supplier_id"],
    )

    # Create shop invitations.
    op.create_table(
        "shop_invitations",

        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("inviter_user_id", sa.Integer(), nullable=False),

        sa.Column("invitee_email", sa.String(150), nullable=True),
        sa.Column("invitee_phone", sa.String(20), nullable=True),

        sa.Column("invitation_type", sa.String(20), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),

        sa.Column("token_hash", sa.String(255), nullable=False),

        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),

        sa.CheckConstraint(
            "invitation_type IN ('employee', 'distributor')",
            name="ck_shop_invitation_type",
        ),

        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'revoked', 'expired')",
            name="ck_shop_invitation_status",
        ),

        sa.CheckConstraint(
            "invitee_email IS NOT NULL OR invitee_phone IS NOT NULL",
            name="ck_shop_invitation_contact",
        ),

        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["inviter_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "token_hash",
            name="uq_shop_invitation_token_hash",
        ),
    )

    op.create_index(
        "ix_shop_invitations_id",
        "shop_invitations",
        ["id"],
    )

    op.create_index(
        "ix_shop_invitations_invitee_email",
        "shop_invitations",
        ["invitee_email"],
    )

    op.create_index(
        "ix_shop_invitations_inviter_user_id",
        "shop_invitations",
        ["inviter_user_id"],
    )

    op.create_index(
        "ix_shop_invitations_shop_id",
        "shop_invitations",
        ["shop_id"],
    )

    op.create_index(
        "ix_shop_invitations_status",
        "shop_invitations",
        ["status"],
    )

    op.create_index(
        "ix_shop_invitations_supplier_id",
        "shop_invitations",
        ["supplier_id"],
    )


# ==========================================
# DOWNGRADE
# Purpose:
# Remove only the two newly created tables.
# ==========================================

def downgrade() -> None:

    op.drop_table("shop_invitations")

    op.drop_table("shop_distributor_connections")
