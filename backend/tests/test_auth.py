"""
KiranaAI authentication security, validation and API tests.
All database-backed tests use the isolated kiranaai_test database.
"""
import pytest
from pydantic import ValidationError

from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
)
from app.auth.schemas import OwnerRegister, DistributorRegister
from app.models.user import User
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.models.shop_membership import ShopMembership


# Password and token security

def test_password_hashing():
    """Verify that passwords are securely hashed and verified."""
    password = "KiranaTest@123"
    hashed_password = hash_password(password)
    assert hashed_password != password
    assert verify_password(password, hashed_password)
    assert not verify_password("WrongPassword@123", hashed_password)


def test_access_token_creation():
    """Verify that a generated token contains the correct identity."""
    token = create_access_token(user_id=123, role="Owner")
    payload = verify_access_token(token)
    assert payload["sub"] == "123"
    assert payload["role"] == "Owner"
    assert "exp" in payload
    assert "iat" in payload


def test_invalid_access_token_is_rejected():
    """Verify that an invalid token cannot be decoded."""
    from jwt.exceptions import InvalidTokenError
    with pytest.raises(InvalidTokenError):
        verify_access_token("this-is-not-a-valid-token")


# Registration schema validation

def test_owner_registration_validation():
    """Verify that valid owner registration details are accepted."""
    owner = OwnerRegister(
        full_name="Test Owner",
        email="owner@example.com",
        password="KiranaTest@123",
        shop_name="Test Kirana Shop",
    )
    assert owner.full_name == "Test Owner"
    assert str(owner.email) == "owner@example.com"
    assert owner.shop_name == "Test Kirana Shop"


def test_owner_registration_rejects_short_password():
    """Verify that owner registration rejects passwords shorter than eight characters."""
    with pytest.raises(ValidationError):
        OwnerRegister(
            full_name="Test Owner",
            email="owner@example.com",
            password="short",
            shop_name="Test Kirana Shop",
        )


def test_distributor_registration_validation():
    """Verify that valid distributor registration details are accepted."""
    distributor = DistributorRegister(
        full_name="Test Distributor",
        email="distributor@example.com",
        password="KiranaTest@123",
        business_name="Test Wholesale Business",
    )
    assert distributor.full_name == "Test Distributor"
    assert distributor.business_name == "Test Wholesale Business"


# Owner registration API

def owner_payload(email="owner@example.com", gstin=None):
    """Build valid owner registration data for API tests."""
    return {
        "full_name": "Test Owner",
        "email": email,
        "phone": "9876543210",
        "password": "KiranaTest@123",
        "shop_name": "Test Kirana Shop",
        "shop_address": "Bengaluru",
        "shop_phone": "9876543210",
        "gstin": gstin,
    }


def test_owner_registration_creates_user_shop_and_membership(client, db_session):
    """Verify owner registration creates all related database records."""
    response = client.post("/auth/register/owner", json=owner_payload())
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "owner@example.com"
    assert data["user"]["role"] == "Owner"
    assert data["shop"]["name"] == "Test Kirana Shop"
    assert data["access_token"]
    assert data["token_type"] == "bearer"

    user = db_session.query(User).filter_by(email="owner@example.com").one()
    shop = db_session.query(Shop).filter_by(name="Test Kirana Shop").one()
    membership = db_session.query(ShopMembership).filter_by(
        user_id=user.id, shop_id=shop.id
    ).one()

    assert user.role == "Owner"
    assert user.password_hash != "KiranaTest@123"
    assert verify_password("KiranaTest@123", user.password_hash)
    assert membership.role == "Owner"
    assert membership.is_active is True


def test_owner_registration_rejects_duplicate_email(client):
    """Verify that an email address cannot register twice."""
    first = client.post("/auth/register/owner", json=owner_payload())
    second = client.post("/auth/register/owner", json=owner_payload())
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "Email is already registered"


def test_owner_registration_rejects_duplicate_gstin(client):
    """Verify that a shop cannot reuse an existing GSTIN."""
    gstin = "29ABCDE1234F1Z5"
    first = client.post(
        "/auth/register/owner",
        json=owner_payload("owner1@example.com", gstin),
    )
    second = client.post(
        "/auth/register/owner",
        json=owner_payload("owner2@example.com", gstin),
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_owner_registration_rejects_invalid_payload(client):
    """Verify that invalid owner registration data is rejected."""
    response = client.post(
        "/auth/register/owner",
        json={
            "full_name": "A",
            "email": "not-an-email",
            "password": "short",
            "shop_name": "X",
        },
    )
    assert response.status_code == 422


# Distributor registration API

def distributor_payload(email="distributor@example.com"):
    """Build valid distributor registration data for API tests."""
    return {
        "full_name": "Test Distributor",
        "email": email,
        "phone": "9876543211",
        "password": "KiranaTest@123",
        "business_name": "Test Wholesale Business",
        "contact_person": "Test Contact",
        "address": "Bengaluru",
    }


def test_distributor_registration_creates_supplier_and_user(client, db_session):
    """Verify distributor registration creates linked supplier and user records."""
    response = client.post(
        "/auth/register/distributor",
        json=distributor_payload(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "distributor@example.com"
    assert data["user"]["role"] == "Supplier"
    assert data["supplier"]["name"] == "Test Wholesale Business"
    assert data["access_token"]

    user = db_session.query(User).filter_by(
        email="distributor@example.com"
    ).one()
    supplier = db_session.query(Supplier).filter_by(
        name="Test Wholesale Business"
    ).one()
    assert user.role == "Supplier"
    assert user.supplier_id == supplier.id
    assert supplier.email == "distributor@example.com"
    assert verify_password("KiranaTest@123", user.password_hash)


def test_distributor_registration_rejects_duplicate_email(client):
    """Verify that a distributor email address cannot register twice."""
    first = client.post(
        "/auth/register/distributor",
        json=distributor_payload(),
    )
    second = client.post(
        "/auth/register/distributor",
        json=distributor_payload(),
    )
    assert first.status_code == 201
    assert second.status_code == 409


# Login API

def test_login_accepts_valid_owner_credentials(client):
    """Verify that a registered owner can log in and receive a token."""
    registration = client.post(
        "/auth/register/owner",
        json=owner_payload(),
    )
    assert registration.status_code == 201

    response = client.post(
        "/auth/login",
        data={
            "username": "owner@example.com",
            "password": "KiranaTest@123",
        },
    )
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_login_rejects_wrong_password(client):
    """Verify that an incorrect password cannot authenticate."""
    registration = client.post(
        "/auth/register/owner",
        json=owner_payload(),
    )
    assert registration.status_code == 201

    response = client.post(
        "/auth/login",
        data={
            "username": "owner@example.com",
            "password": "WrongPassword@123",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_rejects_unknown_email(client):
    """Verify that an unknown email address cannot authenticate."""
    response = client.post(
        "/auth/login",
        data={
            "username": "unknown@example.com",
            "password": "KiranaTest@123",
        },
    )
    assert response.status_code == 401


def test_login_rejects_inactive_account(client, db_session):
    """Verify that an inactive account cannot authenticate."""
    user = User(
        full_name="Inactive Owner",
        email="inactive@example.com",
        password_hash=hash_password("KiranaTest@123"),
        role="Owner",
        is_active=False,
    )
    db_session.add(user)
    db_session.flush()

    response = client.post(
        "/auth/login",
        data={
            "username": "inactive@example.com",
            "password": "KiranaTest@123",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"


# Authenticated shop membership endpoint

def test_my_shops_returns_only_active_memberships(client):
    registration = client.post("/auth/register/owner", json=owner_payload())
    token = registration.json()["access_token"]

    response = client.get(
        "/auth/shops",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == [{
        "shop_id": registration.json()["shop"]["id"],
        "name": "Test Kirana Shop",
        "address": "Bengaluru",
        "role": "Owner",
    }]


def test_my_shops_requires_authentication(client):
    response = client.get("/auth/shops")
    assert response.status_code == 401

# Authenticated account endpoint

def test_account_endpoint_rejects_missing_token(client):
    """Verify that private account details require authentication."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_account_endpoint_rejects_invalid_token(client):
    """Verify that an invalid bearer token cannot access account details."""
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
