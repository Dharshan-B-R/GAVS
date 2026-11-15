"""Stockout risk estimates using recorded sales velocity and saleable batch stock."""
from sqlalchemy.orm import Session

from app.services.inventory_intelligence_service import get_stock_coverage


def predict_stockout_risk(
    db: Session,
    shop_id: int,
    history_days: int = 30,
    lead_time_days: int = 7,
    warning_days: int = 14,
    limit: int = 100,
) -> dict:
    if not 7 <= history_days <= 365:
        raise ValueError("History window must be between 7 and 365 days")
    if not 1 <= lead_time_days <= 90:
        raise ValueError("Lead time must be between 1 and 90 days")
    if not 1 <= warning_days <= 90:
        raise ValueError("Warning window must be between 1 and 90 days")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    coverage = get_stock_coverage(
        db, days=history_days, limit=limit, warning_days=warning_days, shop_id=shop_id
    )
    products = []
    counts = {"stockout": 0, "before_lead_time": 0, "within_warning_window": 0, "low_risk": 0, "unknown": 0}
    for row in coverage["products"]:
        days_left = row["estimated_days_remaining"]
        if row["saleable_stock"] <= 0:
            risk = "stockout"
            counts["stockout"] += 1
        elif days_left is None:
            risk = "unknown"
            counts["unknown"] += 1
        elif days_left <= lead_time_days:
            risk = "before_lead_time"
            counts["before_lead_time"] += 1
        elif days_left <= warning_days:
            risk = "within_warning_window"
            counts["within_warning_window"] += 1
        else:
            risk = "low_risk"
            counts["low_risk"] += 1
        products.append({
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "saleable_stock": row["saleable_stock"],
            "average_daily_sales": row["average_daily_sales"],
            "estimated_days_remaining": days_left,
            "lead_time_days": lead_time_days,
            "risk": risk,
            "recommended_attention": (
                "Immediate review: no verified unexpired saleable stock"
                if risk == "stockout" else
                "Escalate replenishment planning; current stock may not cover supplier lead time"
                if risk == "before_lead_time" else
                "Monitor and include in the next owner-reviewed purchase plan"
                if risk == "within_warning_window" else
                "No immediate action indicated by recorded sales velocity"
                if risk == "low_risk" else
                "Insufficient recorded sales to estimate stockout timing"
            ),
        })
    priority = {"stockout": 0, "before_lead_time": 1, "within_warning_window": 2, "unknown": 3, "low_risk": 4}
    products.sort(key=lambda item: (priority[item["risk"]], item["estimated_days_remaining"] if item["estimated_days_remaining"] is not None else float("inf"), item["product_name"]))
    return {
        "analysis": "stockout_risk",
        "shop_id": shop_id,
        "history_days": history_days,
        "lead_time_days": lead_time_days,
        "warning_days": warning_days,
        "summary": counts,
        "count": len(products),
        "products": products,
        "limitations": [
            "Uses recorded sale stock movements and verified unexpired batch stock",
            "Assumes historical average daily sales continue; this is not a seasonal forecast",
            "Cannot estimate demand lost while the product was out of stock",
            "Does not account for supplier delays unless reflected in the lead-time input",
            "Recommendations are informational; owner approval remains required for purchases",
        ],
    }
