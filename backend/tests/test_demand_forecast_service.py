"""Tests for deterministic demand forecast and reorder recommendations."""
from datetime import datetime, timedelta, timezone, date

import pytest

from app.models.product import Product
from app.models.shop import Shop
from app.models.stock_movement import StockMovement
from app.models.product_batch import ProductBatch
from app.services.demand_forecast_service import forecast_demand
from app.services.reorder_service import build_reorder_recommendations


def _product(db, **overrides):
    if db.get(Shop, 1) is None:
        db.add(Shop(id=1, name="Forecast Test Shop"))
        db.flush()

    values = {
        "shop_id": 1,
        "name": "Forecast Rice",
        "category": "Grocery",
        "quantity": 20,
        "minimum_stock": 5,
        "purchase_price": 10,
        "selling_price": 15,
        "unit": "kg",
        "is_active": True,
        "created_at": datetime.now(timezone.utc) - timedelta(days=120),
    }
    values.update(overrides)
    product = Product(**values)
    db.add(product)
    db.flush()
    return product


def test_forecast_uses_recorded_sale_movements(db_session):
    product = _product(db_session)
    db_session.add(StockMovement(
        product_id=product.id, movement_type="sale",
        quantity_change=-60, quantity_before=80, quantity_after=20,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    ))
    db_session.flush()

    result = forecast_demand(db_session, days=30)
    row = next(p for p in result["products"] if p["product_id"] == product.id)

    assert row["units_sold"] == 60
    assert row["average_daily_demand"] == 2
    assert row["forecast_next_30_days"] == 60
    assert row["confidence"] == "medium"


def test_reorder_uses_verified_unexpired_stock_only(db_session):
    product = _product(db_session, quantity=100, minimum_stock=5)
    db_session.add_all([
        ProductBatch(
            product_id=product.id, batch_number="GOOD",
            expiry_date=date.today() + timedelta(days=60),
            quantity=5, purchase_price=10, is_verified=True,
        ),
        ProductBatch(
            product_id=product.id, batch_number="UNVERIFIED",
            expiry_date=date.today() + timedelta(days=60),
            quantity=40, purchase_price=10, is_verified=False,
        ),
    ])
    db_session.add(StockMovement(
        product_id=product.id, movement_type="sale",
        quantity_change=-60, quantity_before=160, quantity_after=100,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    ))
    db_session.flush()

    result = build_reorder_recommendations(
        db_session, days=30, lead_time_days=7, safety_days=3
    )
    row = next(p for p in result["recommendations"] if p["product_id"] == product.id)

    assert row["saleable_stock"] == 5
    assert row["suggested_quantity"] == 15
    assert row["estimated_total_cost"] == 150


@pytest.mark.parametrize("days", [0, 6, 366])
def test_forecast_rejects_invalid_history_window(db_session, days):
    with pytest.raises(ValueError):
        forecast_demand(db_session, days=days)
