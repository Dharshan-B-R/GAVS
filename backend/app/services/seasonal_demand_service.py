"""Observed monthly demand patterns; no festival uplift is assumed."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.shop import Shop


def analyze_seasonal_demand(
    db: Session, shop_id: int, history_days: int = 365, limit: int = 50
) -> dict:
    if not 300 <= history_days <= 730:
        raise ValueError("Seasonality history must be between 300 and 730 days")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if shop is None:
        raise ValueError("Shop not found")
    # PostgreSQL timezone() converts stored UTC timestamps into the shop's
    # configured local clock before month/day grouping.
    local_created_at = func.timezone(shop.timezone or "Asia/Kolkata", StockMovement.created_at)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=history_days)
    month_expr = func.extract("month", local_created_at).label("month")
    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.unit,
            month_expr,
            func.sum(-StockMovement.quantity_change).label("units_sold"),
            func.count(func.distinct(func.date(local_created_at))).label("selling_days"),
        )
        .join(StockMovement, StockMovement.product_id == Product.id)
        .filter(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            StockMovement.movement_type == "sale",
            StockMovement.quantity_change < 0,
            StockMovement.created_at >= start,
            StockMovement.created_at <= end,
        )
        .group_by(Product.id, Product.name, Product.unit, month_expr)
        .order_by(Product.name, month_expr)
        .all()
    )

    grouped = {}
    for product_id, name, unit, month, units, selling_days in rows:
        item = grouped.setdefault(product_id, {
            "product_id": product_id, "product_name": name, "unit": unit, "months": {}
        })
        item["months"][int(month)] = {
            "units_sold": round(float(units or 0), 3),
            "selling_days": int(selling_days or 0),
        }

    products = []
    insufficient = 0
    for item in grouped.values():
        observed = item["months"]
        if len(observed) < 6:
            insufficient += 1
            products.append({
                **item, "status": "insufficient_monthly_coverage",
                "observed_month_count": len(observed),
                "monthly_pattern": [],
            })
            continue
        average = sum(v["units_sold"] for v in observed.values()) / len(observed)
        pattern = []
        for month in range(1, 13):
            value = observed.get(month)
            pattern.append({
                "month": month,
                "units_sold": value["units_sold"] if value else None,
                "selling_days": value["selling_days"] if value else 0,
                "seasonal_index": round(value["units_sold"] / average, 3) if value and average > 0 else None,
                "observed": value is not None,
            })
        products.append({
            "product_id": item["product_id"], "product_name": item["product_name"],
            "unit": item["unit"], "status": "observed_pattern",
            "observed_month_count": len(observed),
            "average_observed_monthly_sales": round(average, 3),
            "monthly_pattern": pattern,
        })

    products.sort(key=lambda p: (p["status"] != "observed_pattern", p["product_name"]))
    products = products[:limit]
    return {
        "analysis": "seasonal_demand",
        "shop_id": shop_id,
        "history_days": history_days,
        "count": len(products),
        "insufficient_coverage_count": sum(p["status"] != "observed_pattern" for p in products),
        "products": products,
        "limitations": [
            "Uses only recorded sale stock movements for the requested shop",
            "A month without recorded sales is shown as unobserved, not assumed zero demand",
            "Observed monthly patterns are descriptive and do not prove seasonal causation",
            "Festival effects, stockout-censored demand, price changes and promotions are not modelled",
            "No forecast uplift is applied; use patterns as decision support only",
        ],
    }
