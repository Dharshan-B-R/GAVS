

# ==========================================
# USER DATABASE MODEL
# Purpose:
# 1. Store user registration and login details.
# 2. Support Admin, Owner, Employee and Supplier roles.
# 3. Store securely hashed passwords.
# 4. Maintain account activation status.
#
# Database table: users
# ==========================================

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey
)
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    full_name = Column(String(150), nullable=False)

    email = Column(
        String(150),
        unique=True,
        index=True,
        nullable=False
    )

    phone = Column(String(20), nullable=True)

    password_hash = Column(String(255), nullable=False)

    role = Column(String(20), nullable=False)

    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=True
    )

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
