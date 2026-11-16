"""Tests for event-window demand comparison."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.product import Product
from app.models.shop import Shop
from app.models.stock_movement import StockMovement
from app.services.event_demand_service import analyze_event_demand


def test_event_demand_compares_event_with_observed_baseline(db_session):
    db_session.add(Shop(id=1, name="Event Shop"))
    db_session.flush()
    product = Product(
        shop_id=1, name="Festival Snack", quantity=10, minimum_stock=1,
        purchase_price=5, selling_price=8, unit="pieces", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    start = date(2026, 11, 1)
    for offset in range(14):
        when = datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=offset * 4)
        db_session.add(StockMovement(
            product_id=product.id, movement_type="sale",
            quantity_change=-2, quantity_before=20, quantity_after=18,
            created_at=when,
        ))
    for offset in range(7):
        when = datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=offset)
        db_session.add(StockMovement(
            product_id=product.id, movement_type="sale",
            quantity_change=-5, quantity_before=20, quantity_after=15,
            created_at=when,
        ))
    db_session.flush()

    result = analyze_event_demand(
        db_session, 1, "Local festival", start, window_days=7, baseline_days=56
    )
    row = result["products"][0]

    assert row["status"] == "observed_increase"
    assert row["event_units_sold"] == 35
    assert row["change_percent_vs_baseline"] is not None


@pytest.mark.parametrize(
    "kwargs",
    [{"event_name": ""}, {"window_days": 0}, {"baseline_days": 10}, {"limit": 0}],
)
def test_event_demand_validates_parameters(db_session, kwargs):
    arguments = {"event_name": "Event", "event_start": date(2026, 11, 1)}
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        analyze_event_demand(db_session, 1, **arguments)


def test_event_demand_rejects_future_or_incomplete_window(db_session):
    db_session.add(Shop(id=1, name="Future Event Shop"))
    db_session.flush()
    with pytest.raises(ValueError, match="completed event window"):
        analyze_event_demand(
            db_session, 1, "Upcoming festival",
            date.today() + timedelta(days=5), window_days=7,
        )
