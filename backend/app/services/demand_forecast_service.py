"""Observed sales forecast with explicit coverage and uncertainty metadata.

This service does not infer sales during stockouts or automatically add seasonal
uplifts. It reports sparse history as low confidence and exposes selling-day
coverage so callers can avoid treating missing observations as zero demand.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.inventory_availability_snapshot import InventoryAvailabilitySnapshot


def forecast_demand(
    db: Session, days: int = 30, limit: int = 50, shop_id: int | None = None
) -> dict:
    if not 7 <= days <= 365:
        raise ValueError("Forecast history window must be between 7 and 365 days")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    query = db.query(
        Product,
        StockMovement.created_at,
        -StockMovement.quantity_change,
    ).join(
        StockMovement, StockMovement.product_id == Product.id
    ).filter(
        Product.is_active.is_(True),
        *([Product.shop_id == shop_id] if shop_id is not None else []),
        StockMovement.movement_type == "sale",
        StockMovement.quantity_change < 0,
        StockMovement.created_at >= start,
        StockMovement.created_at <= end,
    ).order_by(Product.name.asc(), StockMovement.created_at.asc())

    observations = defaultdict(lambda: {
        "units": 0.0, "selling_days": set(), "weekday_units": defaultdict(float),
        "daily_units": defaultdict(float), "months": set(),
    })
    for product, timestamp, quantity in query.all():
        units = float(quantity or 0)
        item = observations[product.id]
        item["units"] += units
        item["selling_days"].add(timestamp.date())
        item["weekday_units"][timestamp.weekday()] += units
        item["daily_units"][timestamp.date()] += units
        item["months"].add(timestamp.month)

    products = []
    product_query = db.query(Product).filter(Product.is_active.is_(True))
    if shop_id is not None:
        product_query = product_query.filter(Product.shop_id == shop_id)
    for product in product_query.order_by(Product.name.asc()).limit(limit).all():
        item = observations[product.id]
        units = item["units"]
        selling_days = len(item["selling_days"])
        snapshots = db.query(InventoryAvailabilitySnapshot).filter(
            InventoryAvailabilitySnapshot.shop_id == product.shop_id,
            InventoryAvailabilitySnapshot.product_id == product.id,
            InventoryAvailabilitySnapshot.snapshot_date >= start.date(),
            InventoryAvailabilitySnapshot.snapshot_date <= end.date(),
        ).all()
        availability_dates = {row.snapshot_date for row in snapshots}
        available_dates = {row.snapshot_date for row in snapshots if row.is_available}
        unavailable_dates = {row.snapshot_date for row in snapshots if not row.is_available}
        availability_coverage = len(availability_dates) / days
        availability_adjusted = len(availability_dates) >= max(7, int(days * 0.5)) and len(available_dates) >= 3
        forecast_units = (
            sum(item["daily_units"].get(day, 0.0) for day in available_dates)
            if availability_adjusted else units
        )
        demand_days = len(available_dates) if availability_adjusted else days
        daily = forecast_units / demand_days if demand_days else 0.0
        coverage = selling_days / days
        weekday_profile = []
        weekday_covered = True
        for weekday in range(7):
            sample_dates = [d for d in item["selling_days"] if d.weekday() == weekday]
            weekday_covered = weekday_covered and len(sample_dates) >= 2
            sample_units = sum(item["daily_units"][d] for d in sample_dates)
            weekday_profile.append({
                "weekday": weekday,
                "observed_selling_days": len(sample_dates),
                "average_units_per_observed_selling_day": (
                    round(sample_units / len(sample_dates), 3) if sample_dates else None
                ),
            })

        if forecast_units <= 0 or selling_days < 3:
            confidence = "low"
        elif availability_adjusted and availability_coverage >= 0.7 and len(available_dates) >= 14:
            confidence = "medium"
        elif not snapshots and days >= 60 and coverage >= 0.25 and selling_days >= 14:
            confidence = "medium"
        else:
            confidence = "low"

        products.append({
            "product_id": product.id,
            "product_name": product.name,
            "history_days": days,
            "units_sold": round(units, 3),
            "selling_days": selling_days,
            "observed_selling_day_ratio": round(coverage, 3),
            "availability_snapshot_days": len(availability_dates),
            "availability_coverage_ratio": round(availability_coverage, 3),
            "observed_stockout_days": len(unavailable_dates),
            "availability_adjusted": availability_adjusted,
            "average_daily_demand": round(daily, 4) if forecast_units > 0 else None,
            "forecast_next_30_days": round(daily * 30, 2) if forecast_units > 0 else None,
            "recorded_stock": float(product.quantity or 0),
            "minimum_stock": float(product.minimum_stock or 0),
            "unit": product.unit,
            "confidence": confidence,
            "weekday_profile": weekday_profile if weekday_covered else None,
            "observed_months": sorted(item["months"]),
            "forecast_method": "availability_adjusted_sales_velocity" if availability_adjusted else "observed_sales_velocity",
        })

    products.sort(key=lambda row: (
        row["confidence"] == "low",
        -(row["forecast_next_30_days"] or 0),
        row["product_name"],
    ))
    return {
        "analysis": "demand_forecast",
        "shop_id": shop_id,
        "history_days": days,
        "products": products,
        "count": len(products),
        "limitations": [
            "Uses recorded sale stock movements only",
            "No-sale and missing observation days are not filled with estimated demand",
            "Availability-adjusted demand is used only when at least half the history window has explicit daily snapshots",
            "Without sufficient snapshots, stockout-censored demand remains unknown and the basic sales-velocity forecast is retained",
            "Weekday profiles are descriptive and do not automatically change the forecast",
            "Festival, weather, promotion and price effects require separate validated observations",
        ],
    }
