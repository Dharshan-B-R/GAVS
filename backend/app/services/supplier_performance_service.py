"""Supplier performance evidence from received purchase history.

The present schema has no promised delivery timestamp, separate ordered and received
quantities, or supplier issue log. Unavailable rates are intentionally left null.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier


def analyze_supplier_performance(db: Session, shop_id: int, limit: int = 100) -> dict:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    rows = (
        db.query(
            Supplier.id, Supplier.name,
            func.count(func.distinct(Purchase.id)),
            func.count(PurchaseItem.id),
            func.coalesce(func.sum(PurchaseItem.quantity), 0),
            func.coalesce(func.sum(PurchaseItem.subtotal), 0),
            func.min(Purchase.purchase_date),
            func.max(Purchase.purchase_date),
        )
        .join(Purchase, Purchase.supplier_id == Supplier.id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .join(Product, Product.id == PurchaseItem.product_id)
        .filter(
            Purchase.shop_id == shop_id, Product.shop_id == shop_id,
            Product.is_active.is_(True), Purchase.status == "received",
            PurchaseItem.quantity > 0,
        )
        .group_by(Supplier.id, Supplier.name)
        .order_by(func.sum(PurchaseItem.subtotal).desc(), Supplier.name.asc())
        .limit(limit).all()
    )
    suppliers = [{
        "supplier_id": row[0], "supplier_name": row[1],
        "received_order_count": int(row[2] or 0),
        "received_invoice_line_count": int(row[3] or 0),
        "received_quantity": round(float(row[4] or 0), 3),
        "recorded_received_value": round(float(row[5] or 0), 2),
        "first_recorded_receipt": row[6], "last_recorded_receipt": row[7],
        "on_time_delivery_rate": None, "fill_rate": None, "issue_rate": None,
        "performance_status": "insufficient_delivery_evidence",
    } for row in rows]
    return {
        "analysis": "supplier_performance", "shop_id": shop_id,
        "supplier_count": len(suppliers), "suppliers": suppliers,
        "unavailable_metrics": {
            "on_time_delivery_rate": "Promised delivery dates are not stored.",
            "fill_rate": "Ordered and received quantities are not stored separately.",
            "issue_rate": "Supplier issue/dispute records are not present.",
        },
        "limitations": [
            "Only completed receipts linked to this shop are included",
            "Receipt dates and received values are historical activity, not reliability scores",
        ],
    }
}