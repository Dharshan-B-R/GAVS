"""Supplier delivery and fill-rate evidence from shop purchase orders.

Rates use only explicit expected delivery dates and separately recorded ordered and
received quantities. Legacy deliveries without promised dates remain outside the
on-time denominator rather than being assumed punctual.
"""
from collections import defaultdict
from datetime import date, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.purchase import Purchase
from app.models.supplier import Supplier
from app.models.supplier_issue import SupplierIssue
from app.models.shop import Shop


def analyze_supplier_performance(db: Session, shop_id: int, limit: int = 100) -> dict:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    local_tz = ZoneInfo(shop.timezone if shop and shop.timezone else "UTC")
    purchases = db.query(Purchase).filter(
        Purchase.shop_id == shop_id,
        Purchase.status.in_(["received", "partially_received"]),
    ).order_by(Purchase.purchase_date.desc()).limit(2000).all()
    grouped = defaultdict(lambda: {
        "orders": 0, "lines": 0, "received_value": 0.0, "received_qty": 0.0,
        "ordered_qty": 0.0, "on_time": 0, "dated_deliveries": 0,
        "first_receipt": None, "last_receipt": None,
    })
    for purchase in purchases:
        supplier = db.query(Supplier).filter(Supplier.id == purchase.supplier_id).first()
        if supplier is None:
            continue
        item = grouped[purchase.supplier_id]
        item["orders"] += 1
        if purchase.received_at is not None:
            received_at = purchase.received_at
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            received_day = received_at.astimezone(local_tz).date()
            item["first_receipt"] = min(item["first_receipt"], received_day) if item["first_receipt"] else received_day
            item["last_receipt"] = max(item["last_receipt"], received_day) if item["last_receipt"] else received_day
            if purchase.expected_delivery_date is not None:
                item["dated_deliveries"] += 1
                if received_day <= purchase.expected_delivery_date:
                    item["on_time"] += 1
        for line in purchase.items:
            item["lines"] += 1
            item["ordered_qty"] += float(line.ordered_quantity if line.ordered_quantity is not None else line.quantity or 0)
            line_received = float(line.received_quantity or 0)
            item["received_qty"] += line_received
            item["received_value"] += line_received * float(line.unit_price or 0)

    result = []
    for supplier_id, item in grouped.items():
        supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
        ordered = item["ordered_qty"]
        received = item["received_qty"]
        issue_rows = db.query(SupplierIssue).filter(
            SupplierIssue.shop_id == shop_id,
            SupplierIssue.supplier_id == supplier_id,
        ).all()
        eligible_purchase_ids = {purchase.id for purchase in purchases if purchase.supplier_id == supplier_id}
        affected_order_ids = {
            issue.purchase_id for issue in issue_rows
            if issue.purchase_id is not None and issue.purchase_id in eligible_purchase_ids
        }
        result.append({
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "received_order_count": item["orders"],
            "received_invoice_line_count": item["lines"],
            "received_quantity": round(received, 3),
            "ordered_quantity": round(ordered, 3),
            "recorded_received_value": round(item["received_value"], 2),
            "first_recorded_receipt": item["first_receipt"],
            "last_recorded_receipt": item["last_receipt"],
            "on_time_delivery_rate": round(item["on_time"] / item["dated_deliveries"], 4) if item["dated_deliveries"] else None,
            "on_time_delivery_sample_count": item["dated_deliveries"],
            "fill_rate": round(min(received / ordered, 1.0), 4) if ordered > 0 else None,
            "supplier_issue_count": len(issue_rows),
            "orders_with_issues": len(affected_order_ids),
            "issue_rate": (
                round(len(affected_order_ids) / item["orders"], 4)
                if issue_rows and affected_order_ids and item["orders"] else None
            ),
            "open_issue_count": sum(1 for issue in issue_rows if issue.status == "open"),
            "performance_status": "measured" if item["dated_deliveries"] or ordered > 0 else "insufficient_delivery_evidence",
        })
    result.sort(key=lambda row: (
        row["on_time_delivery_rate"] is None,
        -(row["on_time_delivery_rate"] or 0),
        row["supplier_name"],
    ))
    result = result[:limit]
    return {
        "analysis": "supplier_performance",
        "shop_id": shop_id,
        "supplier_count": len(result),
        "suppliers": result,
        "unavailable_metrics": {
            "issue_rate": "Calculated as received orders with a linked issue divided by received orders; unlinked issues are reported as counts only.",
            "on_time_delivery_rate": "Only orders with an explicitly recorded expected delivery date and receipt timestamp contribute.",
        },
        "limitations": [
            "Legacy receipts without received_at or expected_delivery_date are excluded from on-time rate",
            "Fill rate uses separately recorded ordered and received quantities; older records are backfilled as fully received",
            "No reliability rating is inferred when there is no eligible evidence",
        ],
    }
