"""
Tests for read-only inventory intelligence calculations.
Uses the isolated db_session fixture configured in tests/conftest.py.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement
from app.services.inventory_intelligence_service import (
    analyze_inventory,
    get_low_stock,
    get_stock_coverage,
)


def _product(db, **overrides):
    """Create a mature active product with predictable inventory values."""
    values = {
        "shop_id": 1,\n        "name": "Test Rice", "category": "Grocery",
        "quantity": 50, "minimum_stock": 10,
        "purchase_price": 20, "selling_price": 25,
        "unit": "kg", "is_active": True,
        "created_at": datetime.now(timezone.utc) - timedelta(days=120),
    }
    values.update(overrides)
    item = Product(**values)
    db.add(item)
    db.flush()
    return item


def test_low_stock_returns_only_products_at_or_below_minimum(db_session):
    _product(db_session, name="Low Rice", quantity=4, minimum_stock=10)
    _product(db_session, name="Healthy Oil", quantity=20, minimum_stock=5)

    result = get_low_stock(db_session)

    assert result["count"] == 1
    assert result["products"][0]["product_name"] == "Low Rice"
    assert result["products"][0]["shortfall"] == 6


def test_stock_coverage_excludes_unverified_and_expired_batches(db_session):
    """
    Recorded stock is 100, but only 30 units are saleable.
    300 units sold over 30 days means 10/day and exactly 3 days coverage.
    """
    product = _product(db_session, quantity=100, minimum_stock=5)
    db_session.add_all([
        ProductBatch(
            product_id=product.id, batch_number="GOOD",
            expiry_date=date.today() + timedelta(days=30),
            quantity=30, purchase_price=20, is_verified=True,
        ),
        ProductBatch(
            product_id=product.id, batch_number="UNVERIFIED",
            expiry_date=date.today() + timedelta(days=30),
            quantity=40, purchase_price=20, is_verified=False,
        ),
        ProductBatch(
            product_id=product.id, batch_number="EXPIRED",
            expiry_date=date.today() - timedelta(days=1),
            quantity=50, purchase_price=20, is_verified=True,
        ),
    ])
    db_session.add(StockMovement(
        product_id=product.id, movement_type="sale",
        quantity_change=-300, quantity_before=400, quantity_after=100,
        reason="Test sales",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.flush()

    result = get_stock_coverage(db_session, days=30)
    row = next(p for p in result["products"] if p["product_id"] == product.id)

    assert row["recorded_stock"] == 100
    assert row["saleable_stock"] == 30
    assert row["units_sold"] == 300
    assert row["average_daily_sales"] == 10
    assert row["estimated_days_remaining"] == 3
    assert row["stock_status"] == "low_stock"


def test_unknown_inventory_intent_is_rejected(db_session):
    with pytest.raises(ValueError, match="Unsupported inventory intent"):
        analyze_inventory(db_session, "place_purchase_order")


@pytest.mark.parametrize("days", [0, -1, 366])
def test_stock_coverage_rejects_invalid_analysis_period(db_session, days):
    with pytest.raises(ValueError, match="days must be between"):
        get_stock_coverage(db_session, days=days)
