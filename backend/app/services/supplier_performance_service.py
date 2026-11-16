"""Supplier delivery and price performance from received purchase records.

Only confirmed received purchase lines are counted. The existing schema does not
record promised delivery dates, ordered quantities versus short receipt quantities,
or dispute outcomes, so those metrics are reported as unavailable rather than
fabricated.
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
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.count(func.distinct(Purchase.id)).label("received_orders"),
            func.count(PurchaseItem.id).label("received_lines"),
            func.coalesce(func.sum(PurchaseItem.quantity), 0).label("received_quantity"),
            func.coalesce(func.sum(PurchaseItem.subtotal), 0).label("received_value"),
            func.min(Purchase.purchase_date).label("first_received_at"),
            func.max(Purchase.purchase_date).label("last_received_at"),
            func.avg(PurchaseItem.unit_price).label("average_recorded_unit_price"),
        )
        .join(Purchase, Purchase.supplier_id == Supplier.id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .join(Product, Product.id == PurchaseItem.product_id)
        .filter(
            Purchase.shop_id == shop_id,
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            Purchase.status == "received",
            PurchaseItem.quantity > 0,
        )
        .group_by(Supplier.id, Supplier.name)
        .order_by(func.sum(PurchaseItem.subtotal).desc(), Supplier.name.asc())
        .limit(limit)
        .all()
    )

    suppliers = []
    for row in rows:
        suppliers.append({
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier_name,
            "received_order_count": int(row.received_orders or 0),
            "received_invoice_line_count": int(row.received_lines or 0),
            "received_quantity": round(float(row.received_quantity or 0), 3),
            "recorded_received_value": round(float(row.received_value or 0), 2),
            "average_recorded_unit_price": (
                round(float(row.average_recorded_unit_price), 2)
                if row.average_recorded_unit_price is not None else None
            ),
            "first_recorded_receipt": row.first_received_at,
            "last_recorded_receipt": row.last_received_at,
            "delivery_reliability": None,
            "fill_rate": None,
            "performance_status": "insufficient_delivery_evidence",
        })

    return {
        "analysis": "supplier_performance",
        "shop_id": shop_id,
        "supplier_count": len(suppliers),
        "suppliers": suppliers,
        "unavailable_metrics": {
            "on_time_delivery_rate": "Promised delivery dates are not stored.",
            "fill_rate": "Ordered quantity and short-receipt quantities are not separately recorded.",
            "dispute_rate": "Supplier issue/dispute records are not present in the current schema.",
        },
        "limitations": [
            "Only received purchase records in the requested shop are included",
            "Purchase dates are recorded receipt dates only when the receiving workflow completed",
            "No reliability score is inferred from sparse delivery observations",
            "Price comparisons do not normalize taxes, freight, discounts, pack size or quality",
        ],
    }
