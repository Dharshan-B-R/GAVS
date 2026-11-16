"""Purchase ranking that respects stock, forecast confidence and owner cash budget.

Recommendations remain informational only. This module never creates a proposal,
purchase order, supplier commitment, or stock movement.
"""
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.services.demand_forecast_service import forecast_demand
from app.services.inventory_intelligence_service import _saleable_subquery


def build_reorder_recommendations(
    db: Session,
    days: int = 30,
    lead_time_days: int = 7,
    safety_days: int = 3,
    limit: int = 50,
    shop_id: int | None = None,
) -> dict:
    if not 1 <= lead_time_days <= 90 or not 0 <= safety_days <= 60:
        raise ValueError("Lead time must be 1-90 days and safety days 0-60")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    forecast = forecast_demand(db, days=days, limit=limit, shop_id=shop_id)
    saleable = _saleable_subquery(db, shop_id)
    budget = None
    if shop_id is not None:
        budget = db.query(ShopPurchaseBudget).filter(
            ShopPurchaseBudget.shop_id == shop_id
        ).first()
    available_budget = (
        Decimal(str(budget.available_amount))
        if budget is not None else None
    )

    candidates = []
    for item in forecast["products"]:
        if item["average_daily_demand"] is None:
            continue
        product = db.query(Product).filter(
            Product.id == item["product_id"],
            *([Product.shop_id == shop_id] if shop_id is not None else []),
        ).first()
        if product is None:
            continue
        saleable_qty = db.query(saleable.c.saleable_stock).filter(
            saleable.c.product_id == product.id
        ).scalar()
        available = float(saleable_qty or 0)
        daily = float(item["average_daily_demand"])
        target = daily * (lead_time_days + safety_days)
        suggested = max(0.0, target - available)
        minimum_shortfall = max(float(product.minimum_stock or 0) - available, 0.0)
        suggested = max(suggested, minimum_shortfall)
        unit_cost = max(float(product.purchase_price or 0), 0.0)
        if suggested <= 0:
            continue

        # Don't round discrete items down if they are sold as whole units;
        # preserve fractional quantity only for products configured in units
        # where fractional sale is typical (e.g. kg/litre).
        precision = 3
        rounded_qty = float(Decimal(str(suggested)).quantize(Decimal("0.001")))
        total_cost = Decimal(str(rounded_qty)) * Decimal(str(unit_cost))
        urgency_days = available / daily if daily > 0 else None
        confidence = item["confidence"]
        risk = (
            "urgent" if urgency_days is not None and urgency_days <= lead_time_days
            else "review" if urgency_days is not None and urgency_days <= lead_time_days + safety_days
            else "planned"
        )
        candidates.append({
            "product_id": product.id,
            "product_name": product.name,
            "saleable_stock": round(available, 3),
            "average_daily_demand": round(daily, 4),
            "estimated_days_remaining": round(urgency_days, 2) if urgency_days is not None else None,
            "lead_time_days": lead_time_days,
            "safety_days": safety_days,
            "target_stock": round(target, 3),
            "suggested_quantity": rounded_qty,
            "unit": product.unit,
            "estimated_unit_cost": round(unit_cost, 2),
            "estimated_total_cost": round(float(total_cost), 2),
            "confidence": confidence,
            "priority": risk,
            "budget_fit": None,
        })

    # Urgent, higher-confidence stock protection receives first consideration.
    priority = {"urgent": 0, "review": 1, "planned": 2}
    confidence_rank = {"medium": 0, "low": 1}
    candidates.sort(key=lambda row: (
        priority[row["priority"]],
        confidence_rank.get(row["confidence"], 2),
        row["estimated_days_remaining"] if row["estimated_days_remaining"] is not None else float("inf"),
        row["product_name"],
    ))

    selected_total = Decimal("0.00")
    selected = []
    deferred = []
    for row in candidates:
        cost = Decimal(str(row["estimated_total_cost"]))
        if available_budget is None:
            row["budget_fit"] = "budget_not_configured"
            row["recommended_within_budget"] = True
            selected.append(row)
            selected_total += cost
        elif cost <= max(available_budget - selected_total, Decimal("0.00")):
            row["budget_fit"] = "within_budget"
            row["recommended_within_budget"] = True
            selected.append(row)
            selected_total += cost
        else:
            row["budget_fit"] = "exceeds_remaining_budget"
            row["recommended_within_budget"] = False
            deferred.append(row)

    return {
        "analysis": "reorder_recommendations",
        "shop_id": shop_id,
        "history_days": days,
        "lead_time_days": lead_time_days,
        "safety_days": safety_days,
        "budget": {
            "configured": available_budget is not None,
            "available_amount": str(available_budget) if available_budget is not None else None,
            "recommended_total": str(selected_total.quantize(Decimal("0.01"))),
            "remaining_after_recommendations": (
                str((available_budget - selected_total).quantize(Decimal("0.01")))
                if available_budget is not None else None
            ),
            "currency": "INR",
        },
        "count": len(candidates),
        "recommendation_count": len(selected),
        "deferred_count": len(deferred),
        "recommendations": selected,
        "deferred_by_budget": deferred,
        "limitations": [
            "Uses verified, unexpired saleable batches and recorded sales velocity",
            "Stockout-censored demand is not estimated",
            "Low-confidence forecasts are visibly flagged and should be reviewed",
            "Budget ranking is a heuristic priority order, not an optimization guarantee",
            "Does not create proposals, contact suppliers, commit cash or place orders",
        ],
    }
