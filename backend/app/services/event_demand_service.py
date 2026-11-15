"""Compare observed sales around a named festival or local event window.

The caller supplies the event dates. The service compares recorded units with
the immediately preceding baseline and never applies a fabricated festival uplift.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.stock_movement import StockMovement


def analyze_event_demand(
    db: Session,
    shop_id: int,
    event_name: str,
    event_start: date,
    window_days: int = 7,
    baseline_days: int = 56,
    limit: int = 50,
) -> dict:
    if not isinstance(event_name, str) or not event_name.strip() or len(event_name) > 100:
        raise ValueError("event_name must contain 1-100 characters")
    if not 1 <= window_days <= 30:
        raise ValueError("window_days must be between 1 and 30")
    if not 28 <= baseline_days <= 180:
        raise ValueError("baseline_days must be between 28 and 180")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    event_end = event_start + timedelta(days=window_days)
    if event_end > date.today() + timedelta(days=1):
        raise ValueError("Event comparison is descriptive and requires a completed event window")
    baseline_start = event_start - timedelta(days=baseline_days)
    event_start_dt = datetime.combine(event_start, time.min, tzinfo=timezone.utc)
    event_end_dt = datetime.combine(event_end, time.min, tzinfo=timezone.utc)
    baseline_start_dt = datetime.combine(baseline_start, time.min, tzinfo=timezone.utc)

    event_rows = (
        db.query(
            StockMovement.product_id,
            func.sum(-StockMovement.quantity_change).label("units"),
        )
        .join(Product, Product.id == StockMovement.product_id)
        .filter(
            Product.shop_id == shop_id, Product.is_active.is_(True),
            StockMovement.movement_type == "sale",
            StockMovement.quantity_change < 0,
            StockMovement.created_at >= event_start_dt,
            StockMovement.created_at < event_end_dt,
        )
        .group_by(StockMovement.product_id).all()
    )
    baseline_rows = (
        db.query(
            StockMovement.product_id,
            func.sum(-StockMovement.quantity_change).label("units"),
            func.count(func.distinct(func.date(StockMovement.created_at))).label("selling_days"),
        )
        .join(Product, Product.id == StockMovement.product_id)
        .filter(
            Product.shop_id == shop_id, Product.is_active.is_(True),
            StockMovement.movement_type == "sale",
            StockMovement.quantity_change < 0,
            StockMovement.created_at >= baseline_start_dt,
            StockMovement.created_at < event_start_dt,
        )
        .group_by(StockMovement.product_id).all()
    )
    event_map = {row.product_id: float(row.units or 0) for row in event_rows}
    baseline_map = {
        row.product_id: (float(row.units or 0), int(row.selling_days or 0))
        for row in baseline_rows
    }
    product_ids = set(event_map) | set(baseline_map)
    products = (
        db.query(Product).filter(
            Product.shop_id == shop_id, Product.is_active.is_(True),
            Product.id.in_(product_ids),
        ).all()
    ) if product_ids else []

    results = []
    insufficient = 0
    for product in products:
        event_units = event_map.get(product.id, 0.0)
        baseline_units, selling_days = baseline_map.get(product.id, (0.0, 0))
        baseline_daily = baseline_units / baseline_days
        expected = baseline_daily * window_days
        if selling_days < 7:
            status = "insufficient_baseline"
            change_pct = None
            insufficient += 1
        elif expected <= 0:
            status = "no_baseline_demand"
            change_pct = None
        else:
            status = "observed_increase" if event_units > expected else (
                "observed_decrease" if event_units < expected else "similar_to_baseline"
            )
            change_pct = round(((event_units - expected) / expected) * 100, 1)
        results.append({
            "product_id": product.id, "product_name": product.name, "unit": product.unit,
            "event_units_sold": round(event_units, 3),
            "baseline_units_sold": round(baseline_units, 3),
            "baseline_selling_days": selling_days,
            "expected_units_at_baseline_rate": round(expected, 3),
            "change_percent_vs_baseline": change_pct,
            "status": status,
        })
    results.sort(key=lambda row: (
        row["status"] == "insufficient_baseline",
        -(row["change_percent_vs_baseline"] or 0),
        row["product_name"],
    ))
    results = results[:limit]
    return {
        "analysis": "event_demand_comparison",
        "shop_id": shop_id,
        "event_name": event_name.strip(),
        "event_start": event_start.isoformat(),
        "event_end_exclusive": event_end.isoformat(),
        "window_days": window_days,
        "baseline_days": baseline_days,
        "count": len(results),
        "insufficient_baseline_count": sum(r["status"] == "insufficient_baseline" for r in results),
        "products": results,
        "limitations": [
            "Event dates are supplied by the caller; no festival calendar is assumed",
            "Comparison is descriptive and does not establish that the event caused a change",
            "Requires at least seven distinct baseline selling days per product for a percentage comparison",
            "Does not correct for stockouts, price changes, promotions, weather or weekday mix",
            "Only recorded sale stock movements from active products in this shop are included",
        ],
    }
