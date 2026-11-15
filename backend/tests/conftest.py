"""
KiranaAI automated test configuration.

All test database operations are restricted to kiranaai_test.
The main kiranaai database must never be used by these tests.
"""
import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db

TEST_DATABASE_NAME = "kiranaai_test"

if engine.url.database != "kiranaai":
    raise RuntimeError(
        "Expected the main application database to be kiranaai. "
        "Check the database configuration before running tests."
    )

test_database_url = engine.url.set(database=TEST_DATABASE_NAME)
if test_database_url.database != TEST_DATABASE_NAME:
    raise RuntimeError("Unsafe test database configuration.")

test_engine = create_engine(test_database_url, pool_pre_ping=True)

# Register every application model before creating the isolated test schema.
model_modules = [
    "app.models.batch_verification",
    "app.models.customer",
    "app.models.expiry_record",
    "app.models.khata_transaction",
    "app.models.product",
    "app.models.product_batch",
    "app.models.purchase",
    "app.models.purchase_item",
    "app.models.purchase_payment",
    "app.models.sale",
    "app.models.sale_item",
    "app.models.shop",
    "app.models.shop_distributor_connection",
    "app.models.shop_invitation",
    "app.models.shop_membership",
    "app.models.stock_movement",
    "app.models.supplier",
    "app.models.user",
]
for module_name in model_modules:
    importlib.import_module(module_name)

# Prevent main.py's import-time create_all() from touching the main database.
with patch.object(Base.metadata, "create_all"):
    from main import app

# This schema operation targets kiranaai_test only.
Base.metadata.create_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Provide one rollback-isolated test database session per test."""
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """Provide a test client using the same isolated session as the test."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
