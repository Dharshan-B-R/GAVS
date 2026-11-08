
# ==========================================
# KIRANA AI - SHOP INVITATION MODEL
#
# Purpose:
# 1. Allow owners to invite employees.
# 2. Allow owners to invite existing distributors.
# 3. Allow new distributors to register through invitations.
# 4. Track invitation acceptance and rejection.
# 5. Support secure, expiring invitation tokens.
# 6. Prevent duplicate invitation tokens.
#
# Database table: shop_invitations
# ==========================================

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class ShopInvitation(Base):
    __tablename__ = "shop_invitations"

    __table_args__ = (
        UniqueConstraint(
            "token_hash",
            name="uq_shop_invitation_token_hash",
        ),

        CheckConstraint(
            "invitee_email IS NOT NULL OR invitee_phone IS NOT NULL",
            name="ck_shop_invitation_contact",
        ),

        CheckConstraint(
            "invitation_type IN ('employee', 'distributor')",
            name="ck_shop_invitation_type",
        ),

        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'revoked', 'expired')",
            name="ck_shop_invitation_status",
        ),
    )

    # Unique invitation identifier.
    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # Shop sending the invitation.
    shop_id = Column(
        Integer,
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Owner or authorized user who sends the invitation.
    inviter_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Email address of the invited person.
    invitee_email = Column(
        String(150),
        nullable=True,
        index=True,
    )

    # Phone number of the invited person.
    invitee_phone = Column(
        String(20),
        nullable=True,
    )

    # Type of invitation: employee or distributor.
    invitation_type = Column(
        String(20),
        nullable=False,
    )

    # Existing supplier record, if inviting an existing distributor.
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Store only the hashed invitation token.
    token_hash = Column(
        String(255),
        nullable=False,
    )

    # Invitation status.
    status = Column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
        index=True,
    )

    # Invitation expiry date and time.
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    # User who accepted the invitation.
    accepted_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Invitation creation date.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Invitation response date.
    responded_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
