"""Cash-aware reorder ranking. Advisory only; it never creates a purchase."""
from decimal import Decimal, ROUND_CEILING

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.services.demand_forecast_service import forecast_demand
from app.services.inventory_intelligence_service import _saleable_subquery


def build_reorder_recommendations(
    db: Session, days: int = 30, lead_time_days: int = 7,
    safety_days: int = 3, limit: int = 50, shop_id: int | None = None,
) -> dict:
    if not 1 <= lead_time_days <= 90 or not 0 <= safety_days <= 60:
        raise ValueError("Lead time must be 1-90 days and safety days 0-60")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    forecast = forecast_demand(db, days=days, limit=limit, shop_id=shop_id)
    saleable = _saleable_subquery(db, shop_id)
    budget_row = db.query(ShopPurchaseBudget).filter(
        ShopPurchaseBudget.shop_id == shop_id
    ).first() if shop_id is not None else None
    budget = Decimal(str(budget_row.available_amount)) if budget_row else None

    candidates = []
    for demand in forecast["products"]:
        daily = demand["average_daily_demand"]
        if daily is None:
            continue
        product = db.query(Product).filter(
            Product.id == demand["product_id"],
            *([Product.shop_id == shop_id] if shop_id is not None else []),
        ).first()
        if product is None:
            continue
        stock = db.query(saleable.c.saleable_stock).filter(
            saleable.c.product_id == product.id
        ).scalar()
        available = float(stock or 0)
        target = float(daily) * (lead_time_days + safety_days)
        suggested = max(target - available, float(product.minimum_stock or 0) - available, 0.0)
        if suggested <= 0:
            continue

        # Retain three decimals for weight/volume; ceil discrete stock units.
        if product.unit.lower() in {"kg", "g", "l", "ml", "litre", "liter"}:
            quantity = Decimal(str(suggested)).quantize(Decimal("0.001"))
        else:
            quantity = Decimal(str(suggested)).to_integral_value(rounding=ROUND_CEILING)
        unit_cost = Decimal(str(max(float(product.purchase_price or 0), 0)))
        total = (quantity * unit_cost).quantize(Decimal("0.01"))
        days_remaining = available / float(daily) if daily > 0 else None
        priority = (
            "urgent" if days_remaining is not None and days_remaining <= lead_time_days
            else "review" if days_remaining is not None and days_remaining <= lead_time_days + safety_days
            else "planned"
        )
        candidates.append({
            "product_id": product.id, "product_name": product.name,
            "saleable_stock": round(available, 3),
            "average_daily_demand": round(float(daily), 4),
            "estimated_days_remaining": round(days_remaining, 2) if days_remaining is not None else None,
            "lead_time_days": lead_time_days, "safety_days": safety_days,
            "target_stock": round(target, 3), "suggested_quantity": float(quantity),
            "unit": product.unit, "estimated_unit_cost": round(float(unit_cost), 2),
            "estimated_total_cost": float(total), "confidence": demand["confidence"],
            "priority": priority,
        })

    priority_order = {"urgent": 0, "review": 1, "planned": 2}
    confidence_order = {"medium": 0, "low": 1}
    candidates.sort(key=lambda row: (
        priority_order[row["priority"]],
        confidence_order.get(row["confidence"], 2),
        row["estimated_days_remaining"] if row["estimated_days_remaining"] is not None else float("inf"),
        row["product_name"],
    ))

    selected, deferred = [], []
    selected_total = Decimal("0.00")
    for row in candidates:
        line_cost = Decimal(str(row["estimated_total_cost"]))
        if budget is None or line_cost <= max(budget - selected_total, Decimal("0.00")):
            row["budget_fit"] = "budget_not_configured" if budget is None else "within_budget"
            selected.append(row)
            selected_total += line_cost
        else:
            row["budget_fit"] = "exceeds_remaining_budget"
            deferred.append(row)

    return {
        "analysis": "reorder_recommendations", "shop_id": shop_id,
        "history_days": days, "lead_time_days": lead_time_days,
        "safety_days": safety_days,
        "budget": {
            "configured": budget is not None,
            "available_amount": str(budget) if budget is not None else None,
            "recommended_total": str(selected_total.quantize(Decimal("0.01"))),
            "remaining_after_recommendations": (
                str((budget - selected_total).quantize(Decimal("0.01")))
                if budget is not None else None
            ),
            "currency": "INR",
        },
        "count": len(candidates), "recommendation_count": len(selected),
        "deferred_count": len(deferred), "recommendations": selected,
        "deferred_by_budget": deferred,
        "limitations": [
            "Uses verified, unexpired saleable batches and recorded sales velocity",
            "Stockout-censored demand is not estimated; low-confidence forecasts are flagged",
            "Budget ranking is a priority heuristic, not a globally optimal knapsack solution",
            "No purchase proposal, order, supplier contact or stock movement is created",
        ],
    }
}