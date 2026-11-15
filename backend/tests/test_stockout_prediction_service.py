"""Tests for deterministic shop-scoped stockout risk estimates."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.shop import Shop
from app.models.stock_movement import StockMovement
from app.services.stockout_prediction_service import predict_stockout_risk


def _product(db, name, quantity=10):
    if db.get(Shop, 1) is None:
        db.add(Shop(id=1, name="Stockout Test Shop"))
        db.flush()
    product = Product(
        shop_id=1, name=name, category="Grocery", quantity=quantity,
        minimum_stock=2, purchase_price=10, selling_price=15,
        unit="pieces", is_active=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    db.add(product)
    db.flush()
    return product


def test_stockout_risk_flags_stock_running_out_before_lead_time(db_session):
    product = _product(db_session, "Fast mover")
    db_session.add(ProductBatch(
        product_id=product.id, batch_number="B1",
        expiry_date=date.today() + timedelta(days=60),
        quantity=4, purchase_price=10, is_verified=True,
    ))
    db_session.add(StockMovement(
        product_id=product.id, movement_type="sale",
        quantity_change=-30, quantity_before=34, quantity_after=4,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    ))
    db_session.flush()

    result = predict_stockout_risk(db_session, 1, history_days=30, lead_time_days=7)
    row = next(item for item in result["products"] if item["product_id"] == product.id)

    assert row["estimated_days_remaining"] == 4
    assert row["risk"] == "before_lead_time"


def test_stockout_risk_does_not_invent_velocity_without_sales(db_session):
    product = _product(db_session, "No sales")
    db_session.add(ProductBatch(
        product_id=product.id, batch_number="B2",
        expiry_date=date.today() + timedelta(days=60),
        quantity=8, purchase_price=10, is_verified=True,
    ))
    db_session.flush()

    result = predict_stockout_risk(db_session, 1)
    row = next(item for item in result["products"] if item["product_id"] == product.id)

    assert row["estimated_days_remaining"] is None
    assert row["risk"] == "unknown"


@pytest.mark.parametrize(
    "kwargs",
    [{"history_days": 6}, {"lead_time_days": 0}, {"warning_days": 0}, {"limit": 101}],
)
def test_stockout_risk_validates_inputs(db_session, kwargs):
    with pytest.raises(ValueError):
        predict_stockout_risk(db_session, 1, **kwargs)
