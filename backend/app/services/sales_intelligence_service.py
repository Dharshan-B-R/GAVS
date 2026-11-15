"""Deterministic, tenant-scoped sales analytics used by the sales specialist."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.sale import Sale
from app.models.sale_item import SaleItem


def analyze_sales(db: Session, shop_id: int, intent: str, days: int = 7, limit: int = 10) -> dict:
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if intent not in {"summary", "daily", "products"}:
        raise ValueError(f"Unsupported sales intent: {intent}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    scoped_sales = db.query(Sale).filter(
        Sale.shop_id == shop_id, Sale.created_at >= start, Sale.created_at <= end
    )

    if intent == "summary":
        totals = scoped_sales.with_entities(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_amount), 0),
        ).first()
        items = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
            Sale, Sale.id == SaleItem.sale_id
        ).filter(Sale.shop_id == shop_id, Sale.created_at >= start, Sale.created_at <= end).scalar()
        bills, revenue = int(totals[0] or 0), float(totals[1] or 0)
        return {
            "analysis": "summary", "analysis_period_days": days,
            "summary": {
                "total_revenue": round(revenue, 2), "total_bills": bills,
                "total_items_sold": round(float(items or 0), 2),
                "average_bill_value": round(revenue / bills, 2) if bills else 0,
            },
            "period": {"start_date": start, "end_date": end},
        }

    if intent == "daily":
        rows = scoped_sales.order_by(Sale.created_at.asc()).all()
        daily = {}
        for sale in rows:
            key = sale.created_at.date().isoformat()
            entry = daily.setdefault(key, {"date": key, "revenue": 0.0, "total_bills": 0, "items_sold": 0.0})
            entry["revenue"] += float(sale.total_amount or 0)
            entry["total_bills"] += 1
            entry["items_sold"] += sum(float(item.quantity or 0) for item in sale.items)
        records = sorted(daily.values(), key=lambda row: row["date"])
        for row in records:
            row["revenue"] = round(row["revenue"], 2)
            row["items_sold"] = round(row["items_sold"], 2)
        peak = max(records, key=lambda row: row["revenue"]) if records else None
        return {"analysis": "daily", "analysis_period_days": days,
                "total_days_with_sales": len(records), "daily_sales": records,
                "highest_sales_day": peak}

    rows = db.query(
        SaleItem.product_id.label("product_id"),
        SaleItem.product_name.label("product_name"),
        SaleItem.unit.label("unit"),
        func.sum(SaleItem.quantity).label("total_quantity_sold"),
        func.sum(SaleItem.subtotal).label("total_revenue"),
        func.count(func.distinct(SaleItem.sale_id)).label("total_bills"),
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.shop_id == shop_id, Sale.created_at >= start, Sale.created_at <= end
    ).group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.unit).order_by(
        func.sum(SaleItem.quantity).desc(), func.sum(SaleItem.subtotal).desc()
    ).limit(limit).all()
    products = [{
        "rank": rank, "product_id": row.product_id, "product_name": row.product_name,
        "unit": row.unit, "total_quantity_sold": round(float(row.total_quantity_sold or 0), 2),
        "total_revenue": round(float(row.total_revenue or 0), 2),
        "total_bills": int(row.total_bills or 0),
    } for rank, row in enumerate(rows, 1)]
    return {"analysis": "products", "analysis_period_days": days,
            "total_products_sold": len(products), "products": products}
