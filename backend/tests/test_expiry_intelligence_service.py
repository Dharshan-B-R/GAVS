"""Tests for shop-scoped expiry and expiry-loss intelligence."""
from datetime import date, timedelta

import pytest

from app.models.expiry_record import ExpiryRecord
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.shop import Shop
from app.services.expiry_intelligence_service import analyze_expiry_risk


def _product(db, name="Milk", shop_id=1, active=True):
    if db.get(Shop, shop_id) is None:
        db.add(Shop(id=shop_id, name=f"Expiry Shop {shop_id}"))
        db.flush()
    product = Product(
        shop_id=shop_id, name=name, category="Dairy", quantity=20,
        minimum_stock=2, purchase_price=20, selling_price=25,
        unit="pieces", is_active=active,
    )
    db.add(product)
    db.flush()
    return product


def test_expiry_risk_reports_batches_and_cost_exposure(db_session):
    product = _product(db_session)
    db_session.add_all([
        ProductBatch(
            product_id=product.id, batch_number="SOON",
            expiry_date=date(2026, 11, 20), quantity=5,
            purchase_price=18, is_verified=True,
        ),
        ProductBatch(
            product_id=product.id, batch_number="LATER",
            expiry_date=date(2027, 2, 1), quantity=10,
            purchase_price=18, is_verified=True,
        ),
    ])
    db_session.flush()

    result = analyze_expiry_risk(
        db_session, shop_id=1, horizon_days=30, as_of=date(2026, 11, 16)
    )

    assert result["batch_count"] == 1
    assert result["total_at_risk_quantity"] == 5
    assert result["estimated_cost_exposure"] == 90
    assert result["batches"][0]["status"] == "expiring_soon"


def test_expiry_loss_deducts_recorded_supplier_credit(db_session):
    product = _product(db_session)
    batch = ProductBatch(
        product_id=product.id, batch_number="EXPIRED",
        expiry_date=date(2026, 10, 1), quantity=0,
        purchase_price=10, is_verified=True,
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(ExpiryRecord(
        batch_id=batch.id, quantity=4, action="disposed",
        credit_amount=15, approval_status="approved",
        action_status="completed",
    ))
    db_session.flush()

    result = analyze_expiry_risk(
        db_session, shop_id=1, as_of=date(2026, 11, 16)
    )

    assert result["recorded_gross_expiry_loss"] == 40
    assert result["recorded_supplier_credits"] == 15
    assert result["recorded_net_expiry_loss"] == 25


def test_expiry_analysis_is_shop_scoped(db_session):
    own = _product(db_session, name="Own product", shop_id=1)
    other = _product(db_session, name="Other product", shop_id=2)
    for product in (own, other):
        db_session.add(ProductBatch(
            product_id=product.id, batch_number="B",
            expiry_date=date(2026, 11, 18), quantity=2,
            purchase_price=5, is_verified=True,
        ))
    db_session.flush()

    result = analyze_expiry_risk(
        db_session, shop_id=1, as_of=date(2026, 11, 16)
    )

    assert {row["product_name"] for row in result["batches"]} == {"Own product"}


@pytest.mark.parametrize("horizon", [0, 366])
def test_expiry_analysis_rejects_invalid_horizon(db_session, horizon):
    with pytest.raises(ValueError):
        analyze_expiry_risk(db_session, shop_id=1, horizon_days=horizon)
