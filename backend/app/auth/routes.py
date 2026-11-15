
# ==========================================
# KIRANA AI - AUTHENTICATION ROUTES
#
# Purpose:
# 1. Register shop owners.
# 2. Register distributors (suppliers).
# 3. Authenticate users.
# 4. Generate access tokens.
# 5. Return authenticated user details.
# 6. Protect private API endpoints.
# ==========================================

from datetime import datetime, timezone, timedelta
import hashlib
import secrets

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from jwt.exceptions import InvalidTokenError

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.models.shop_membership import ShopMembership
from app.models.shop_invitation import ShopInvitation

from app.auth.schemas import (
    OwnerRegister,
    DistributorRegister,
    TokenResponse,
    UserResponse,
    EmployeeInviteCreate,
    EmployeeInviteAccept,
)

from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
)


# ==========================================
# ROUTER CONFIGURATION
# ==========================================

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


# ==========================================
# REGISTER SHOP OWNER
# Purpose:
# Create an owner account, shop and membership
# in one database transaction.
# ==========================================

@router.post(
    "/register/owner",
    status_code=status.HTTP_201_CREATED,
)
def register_owner(
    owner_data: OwnerRegister,
    db: Session = Depends(get_db),
):

    try:
        email = str(owner_data.email).strip().lower()

        existing_user = db.query(User).filter(
            User.email == email
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="Email is already registered",
            )

        user = User(
            full_name=owner_data.full_name.strip(),
            email=email,
            phone=owner_data.phone,
            password_hash=hash_password(owner_data.password),
            role="Owner",
            is_active=True,
        )

        db.add(user)
        db.flush()

        shop = Shop(
            name=owner_data.shop_name.strip(),
            address=owner_data.shop_address,
            phone=owner_data.shop_phone,
            email=(
                str(owner_data.shop_email).strip().lower()
                if owner_data.shop_email else None
            ),
            gstin=(
                owner_data.gstin.strip().upper()
                if owner_data.gstin else None
            ),
            is_active=True,
        )

        db.add(shop)
        db.flush()

        membership = ShopMembership(
            user_id=user.id,
            shop_id=shop.id,
            role="Owner",
            is_active=True,
        )

        db.add(membership)
        db.commit()

        db.refresh(user)
        db.refresh(shop)

        token = create_access_token(
            user_id=user.id,
            role=user.role,
        )

        return {
            "message": "Shop owner registered successfully",
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
            },
            "shop": {
                "id": shop.id,
                "name": shop.name,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or shop GSTIN already exists",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to register shop owner",
        )


# ==========================================
# REGISTER DISTRIBUTOR / SUPPLIER
# Purpose:
# Create a supplier business record and
# its associated login account.
# ==========================================

@router.post(
    "/register/distributor",
    status_code=status.HTTP_201_CREATED,
)
def register_distributor(
    distributor_data: DistributorRegister,
    db: Session = Depends(get_db),
):

    try:
        email = str(distributor_data.email).strip().lower()

        existing_user = db.query(User).filter(
            User.email == email
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="Email is already registered",
            )

        supplier = Supplier(
            name=distributor_data.business_name.strip(),
            contact_person=(
                distributor_data.contact_person.strip()
                if distributor_data.contact_person else None
            ),
            phone=distributor_data.phone,
            email=email,
            address=distributor_data.address,
            gstin=(
                distributor_data.gstin.strip().upper()
                if distributor_data.gstin else None
            ),
            is_active=True,
        )

        db.add(supplier)
        db.flush()

        user = User(
            full_name=distributor_data.full_name.strip(),
            email=email,
            phone=distributor_data.phone,
            password_hash=hash_password(distributor_data.password),
            role="Supplier",
            supplier_id=supplier.id,
            is_active=True,
        )

        db.add(user)
        db.commit()

        db.refresh(user)
        db.refresh(supplier)

        token = create_access_token(
            user_id=user.id,
            role=user.role,
        )

        return {
            "message": "Distributor registered successfully",
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
                "supplier_id": supplier.id,
            },
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or supplier GSTIN already exists",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to register distributor",
        )


# ==========================================
# LOGIN
# Purpose:
# Verify user credentials and issue an access token.
# ==========================================

@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):

    email = form_data.username.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user or not verify_password(
        form_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


# ==========================================
# GET CURRENT AUTHENTICATED USER
# Purpose:
# Verify the access token and retrieve the
# latest user information from the database.
# ==========================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = verify_access_token(token)

        user_id = payload.get("sub")

        if not user_id:
            raise credentials_exception

        user_id = int(user_id)

    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if not user or not user.is_active:
        raise credentials_exception

    return user





# ==========================================
# ROLE-BASED ACCESS CONTROL
# Purpose:
# Allow API access only to users with
# specifically authorized roles.
# ==========================================

# ------------------------------------------
# CHECK USER ROLE
# Purpose:
# Create a reusable permission checker
# for one or more allowed roles.
# ------------------------------------------

def require_roles(*allowed_roles: str):

    allowed = {
        role.strip().lower()
        for role in allowed_roles
    }

    def role_checker(
        current_user: User = Depends(get_current_user),
    ):

        user_role = current_user.role.strip().lower()

        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )

        return current_user

    return role_checker


# ==========================================
# ROLE PERMISSION DEPENDENCIES
# Purpose:
# Provide reusable permissions for each
# KiranaAI user role.
# ==========================================

require_owner = require_roles("Owner")

require_employee = require_roles("Employee")

require_supplier = require_roles("Supplier")

require_admin = require_roles("Admin")





# ==========================================
# SHOP MEMBERSHIP ACCESS CONTROL
# Purpose:
# Verify that a user belongs to the requested
# shop and has the required membership role.
# ==========================================

# ------------------------------------------
# CHECK SHOP MEMBERSHIP
# Purpose:
# Allow access only when the logged-in user
# has an active membership in the requested
# shop with an authorized membership role.
# ------------------------------------------

def require_shop_membership(*allowed_membership_roles: str):

    allowed = {
        role.strip().lower()
        for role in allowed_membership_roles
    }

    def membership_checker(
        shop_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):

        membership = db.query(ShopMembership).filter(
            ShopMembership.user_id == current_user.id,
            ShopMembership.shop_id == shop_id,
            ShopMembership.is_active.is_(True),
        ).first()

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this shop",
            )

        membership_role = membership.role.strip().lower()
        account_role = current_user.role.strip().lower()

        if membership_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your shop membership does not allow this action",
            )

        if account_role != membership_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account role does not match your shop membership",
            )

        return membership

    return membership_checker


# ==========================================
# SHOP-SPECIFIC PERMISSIONS
# Purpose:
# Provide reusable shop access dependencies.
# ==========================================

require_shop_owner = require_shop_membership("Owner")

require_shop_employee = require_shop_membership("Employee")

require_shop_staff = require_shop_membership("Owner", "Employee")





# ==========================================
# DISTRIBUTOR ACCESS CONTROL
# Purpose:
# Ensure distributors can access only their
# own supplier business records.
# ==========================================

# ------------------------------------------
# VERIFY DISTRIBUTOR ACCOUNT
# Purpose:
# Check that the logged-in user is an active
# distributor linked to a valid supplier.
# ------------------------------------------

def get_current_distributor(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role != "Supplier":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Distributor access required",
        )

    if not current_user.supplier_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No distributor business is linked to this account",
        )

    supplier = db.query(Supplier).filter(
        Supplier.id == current_user.supplier_id,
        Supplier.is_active.is_(True),
    ).first()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Distributor business is inactive or unavailable",
        )

    return supplier


# ------------------------------------------
# VERIFY DISTRIBUTOR OWNERSHIP
# Purpose:
# Prevent a distributor from accessing
# another distributor's business record.
# ------------------------------------------

def require_own_distributor(
    supplier_id: int,
    current_supplier: Supplier = Depends(get_current_distributor),
):

    if current_supplier.id != supplier_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot access another distributor's records",
        )

    return current_supplier





# ==========================================
# GET MY ACCOUNT
# Purpose:
# Return details of the authenticated user.
# ==========================================

@router.get("/shops")
def get_my_shops(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return only active shops the authenticated user actively belongs to."""
    memberships = db.query(ShopMembership, Shop).join(
        Shop, Shop.id == ShopMembership.shop_id
    ).filter(
        ShopMembership.user_id == current_user.id,
        ShopMembership.is_active.is_(True),
        Shop.is_active.is_(True),
    ).order_by(Shop.name.asc()).all()

    return [
        {
            "shop_id": shop.id,
            "name": shop.name,
            "address": shop.address,
            "role": membership.role,
        }
        for membership, shop in memberships
    ]

@router.get("/me", response_model=UserResponse)
def get_my_account(
    current_user: User = Depends(get_current_user),
):

    return current_user


# ==========================================
# EMPLOYEE INVITATIONS
# Owners create time-limited, single-use invitations.
# Only a hash of the invitation token is stored.
# ==========================================

@router.post("/shops/{shop_id}/employees/invitations", status_code=201)
def invite_employee(
    shop_id: int,
    payload: EmployeeInviteCreate,
    membership=Depends(require_shop_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "This email already has an account")
    pending = db.query(ShopInvitation).filter(
        ShopInvitation.shop_id == shop_id,
        ShopInvitation.invitee_email == email,
        ShopInvitation.invitation_type == "employee",
        ShopInvitation.status == "pending",
    ).first()
    if pending and pending.expires_at > datetime.now(timezone.utc):
        raise HTTPException(409, "A pending invitation already exists for this email")

    raw_token = secrets.token_urlsafe(32)
    invitation = ShopInvitation(
        shop_id=shop_id,
        inviter_user_id=current_user.id,
        invitee_email=email,
        invitation_type="employee",
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return {
        "invitation_id": invitation.id,
        "email": email,
        "role": "Employee",
        "expires_at": invitation.expires_at,
        "invitation_token": raw_token,
        "message": "Share this token securely with the invited employee. It is shown only once.",
    }


@router.get("/shops/{shop_id}/employees/invitations")
def list_employee_invitations(
    shop_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    rows = db.query(ShopInvitation).filter(
        ShopInvitation.shop_id == shop_id,
        ShopInvitation.invitation_type == "employee",
    ).order_by(ShopInvitation.created_at.desc()).limit(100).all()
    now = datetime.now(timezone.utc)
    return [{
        "invitation_id": row.id,
        "email": row.invitee_email,
        "status": "expired" if row.status == "pending" and row.expires_at <= now else row.status,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    } for row in rows]


@router.post("/employees/accept-invitation", status_code=201)
def accept_employee_invitation(
    payload: EmployeeInviteAccept,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(payload.invitation_token.encode()).hexdigest()
    invitation = db.query(ShopInvitation).filter(
        ShopInvitation.token_hash == token_hash,
        ShopInvitation.invitation_type == "employee",
    ).with_for_update().first()
    if invitation is None or invitation.status != "pending":
        raise HTTPException(404, "Invitation is invalid or already used")
    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        invitation.status = "expired"
        db.commit()
        raise HTTPException(410, "Invitation has expired")

    email = (invitation.invitee_email or "").strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account already exists for this invitation email")

    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role="Employee",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(ShopMembership(
        user_id=user.id,
        shop_id=invitation.shop_id,
        role="Employee",
        is_active=True,
    ))
    invitation.status = "accepted"
    invitation.accepted_by_user_id = user.id
    invitation.responded_at = now
    db.commit()
    db.refresh(user)
    return {
        "message": "Employee account created and shop membership activated",
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role},
        "shop_id": invitation.shop_id,
    }
