"""Deterministic demand estimates from recorded sale stock movements."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.stock_movement import StockMovement


def forecast_demand(db: Session, days: int = 30, limit: int = 50) -> dict:
    if not 7 <= days <= 365:
        raise ValueError("Forecast history window must be between 7 and 365 days")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    rows = db.query(
        Product,
        func.coalesce(func.sum(-StockMovement.quantity_change), 0).label("sold"),
    ).outerjoin(
        StockMovement,
        (StockMovement.product_id == Product.id)
        & (StockMovement.movement_type == "sale")
        & (StockMovement.quantity_change < 0)
        & (StockMovement.created_at >= start)
        & (StockMovement.created_at <= end),
    ).filter(Product.is_active.is_(True)).group_by(Product.id).order_by(Product.name).limit(limit).all()
    forecasts = []
    for product, sold in rows:
        units = float(sold or 0)
        daily = units / days
        forecasts.append({
            "product_id": product.id, "product_name": product.name,
            "history_days": days, "units_sold": round(units, 3),
            "average_daily_demand": round(daily, 4),
            "forecast_next_30_days": round(daily * 30, 2),
            "recorded_stock": float(product.quantity or 0),
            "minimum_stock": float(product.minimum_stock or 0),
            "unit": product.unit,
            "confidence": "low" if units == 0 else ("medium" if days < 60 else "baseline"),
        })
    return {"analysis": "demand_forecast", "history_days": days, "products": forecasts, "count": len(forecasts),
            "limitations": ["Uses recorded sale stock movements only", "Does not infer censored demand during stockouts",
                            "Does not yet model festivals, weather, price changes or supplier lead-time variability"]}
