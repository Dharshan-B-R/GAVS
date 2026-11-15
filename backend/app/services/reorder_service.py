"""Reorder quantity calculations. Suggestions only; never place orders."""
from sqlalchemy.orm import Session
from app.services.demand_forecast_service import forecast_demand
from app.services.inventory_intelligence_service import _saleable_subquery
from app.models.product import Product


def build_reorder_recommendations(db: Session, days: int = 30, lead_time_days: int = 7,
                                  safety_days: int = 3, limit: int = 50, shop_id: int | None = None) -> dict:
    if not 1 <= lead_time_days <= 90 or not 0 <= safety_days <= 60:
        raise ValueError("Lead time must be 1-90 days and safety days 0-60")
    forecast = forecast_demand(db, days=days, limit=limit, shop_id=shop_id)
    saleable = _saleable_subquery(db, shop_id)
    result = []
    for item in forecast["products"]:
        product = db.query(Product).filter(Product.id == item["product_id"], *([Product.shop_id == shop_id] if shop_id is not None else [])).first()
        if product is None:
            continue
        saleable_qty = db.query(saleable.c.saleable_stock).filter(
            saleable.c.product_id == product.id
        ).scalar()
        available = float(saleable_qty or 0)
        daily = item["average_daily_demand"]
        target = daily * (lead_time_days + safety_days)
        suggested = max(0, target - available)
        if available <= float(product.minimum_stock or 0):
            suggested = max(suggested, float(product.minimum_stock or 0) - available)
        if suggested > 0:
            unit_cost = float(product.purchase_price or 0)
            result.append({
                "product_id": product.id, "product_name": product.name,
                "saleable_stock": available, "average_daily_demand": daily,
                "lead_time_days": lead_time_days, "safety_days": safety_days,
                "suggested_quantity": round(suggested, 3), "unit": product.unit,
                "estimated_unit_cost": round(unit_cost, 2),
                "estimated_total_cost": round(suggested * unit_cost, 2),
                "confidence": item["confidence"],
            })
    result.sort(key=lambda x: (-x["estimated_total_cost"], x["product_name"]))
    return {"analysis": "reorder_recommendations", "history_days": days,
            "lead_time_days": lead_time_days, "safety_days": safety_days,
            "count": len(result), "recommendations": result}
