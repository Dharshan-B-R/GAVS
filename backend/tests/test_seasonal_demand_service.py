"""Tests for observed monthly seasonal demand patterns."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.product import Product
from app.models.shop import Shop
from app.models.stock_movement import StockMovement
from app.services.seasonal_demand_service import analyze_seasonal_demand


def _product(db):
    if db.get(Shop, 1) is None:
        db.add(Shop(id=1, name="Seasonality Test Shop"))
        db.flush()
    product = Product(
        shop_id=1, name="Seasonal Product", category="Grocery",
        quantity=20, minimum_stock=2, purchase_price=10, selling_price=15,
        unit="pieces", is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def test_seasonality_reports_only_observed_months(db_session):
    product = _product(db_session)
    now = datetime.now(timezone.utc)
    for month_offset in range(8):
        when = now - timedelta(days=month_offset * 30)
        db_session.add(StockMovement(
            product_id=product.id, movement_type="sale",
            quantity_change=-float(month_offset + 1),
            quantity_before=100, quantity_after=90,
            created_at=when,
        ))
    db_session.flush()

    result = analyze_seasonal_demand(db_session, 1, history_days=365)
    row = next(p for p in result["products"] if p["product_id"] == product.id)

    assert row["status"] == "observed_pattern"
    assert row["observed_month_count"] >= 6
    assert all(
        item["units_sold"] is None
        for item in row["monthly_pattern"] if not item["observed"]
    )


def test_seasonality_marks_sparse_history_insufficient(db_session):
    product = _product(db_session)
    db_session.add(StockMovement(
        product_id=product.id, movement_type="sale",
        quantity_change=-2, quantity_before=10, quantity_after=8,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.flush()

    result = analyze_seasonal_demand(db_session, 1)
    row = next(p for p in result["products"] if p["product_id"] == product.id)
    assert row["status"] == "insufficient_monthly_coverage"


@pytest.mark.parametrize("kwargs", [{"history_days": 299}, {"history_days": 731}, {"limit": 0}])
def test_seasonality_validates_parameters(db_session, kwargs):
    with pytest.raises(ValueError):
        analyze_seasonal_demand(db_session, 1, **kwargs)
