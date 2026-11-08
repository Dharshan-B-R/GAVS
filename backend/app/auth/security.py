
# ==========================================
# KIRANA AI - AUTHENTICATION SECURITY
#
# Purpose:
# 1. Securely hash user passwords using Argon2.
# 2. Verify passwords during login.
# 3. Generate signed access tokens.
# 4. Verify access tokens.
# 5. Identify expired or invalid tokens.
# ==========================================

import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash


# ==========================================
# SECURITY CONFIGURATION
# ==========================================

SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured with at least 32 characters"
    )

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hasher = PasswordHash.recommended()


# ==========================================
# HASH PASSWORD
# Purpose:
# Convert a plain-text password into a secure Argon2 hash.
# ==========================================

def hash_password(password: str) -> str:
    return password_hasher.hash(password)


# ==========================================
# VERIFY PASSWORD
# Purpose:
# Compare a login password with its stored hash.
# ==========================================

def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hasher.verify(
        plain_password,
        hashed_password,
    )


# ==========================================
# CREATE ACCESS TOKEN
# Purpose:
# Generate a signed token containing the user identity.
# ==========================================

def create_access_token(
    user_id: int,
    role: str,
) -> str:

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ==========================================
# VERIFY ACCESS TOKEN
# Purpose:
# Verify token signature and expiration.
# ==========================================

def verify_access_token(token: str) -> dict:

    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
