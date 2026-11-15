"""Supplier price intelligence from completed, recorded purchase invoices."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier


def compare_supplier_prices(db: Session, shop_id: int, limit: int = 100) -> dict:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    rows = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.unit.label("unit"),
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.min(PurchaseItem.unit_price).label("lowest_price"),
            func.max(PurchaseItem.unit_price).label("highest_price"),
            func.sum(PurchaseItem.quantity).label("purchased_quantity"),
            func.sum(PurchaseItem.subtotal).label("purchase_value"),
            func.count(PurchaseItem.id).label("invoice_line_count"),
        )
        .join(PurchaseItem, PurchaseItem.product_id == Product.id)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(Supplier, Supplier.id == Purchase.supplier_id)
        .filter(
            Purchase.shop_id == shop_id,
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            Purchase.status == "received",
            PurchaseItem.quantity > 0,
        )
        .group_by(Product.id, Product.name, Product.unit, Supplier.id, Supplier.name)
        .order_by(Product.name, Supplier.name)
        .limit(limit)
        .all()
    )
    by_product = {}
    for row in rows:
        quantity = float(row.purchased_quantity or 0)
        value = float(row.purchase_value or 0)
        weighted = value / quantity if quantity > 0 else None
        by_product.setdefault(row.product_id, {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "unit": row.unit,
            "suppliers": [],
        })["suppliers"].append({
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier_name,
            "lowest_recorded_unit_price": round(float(row.lowest_price), 2),
            "highest_recorded_unit_price": round(float(row.highest_price), 2),
            "weighted_average_unit_price": round(weighted, 2) if weighted is not None else None,
            "purchased_quantity": round(quantity, 3),
            "recorded_purchase_value": round(value, 2),
            "invoice_line_count": int(row.invoice_line_count),
        })

    products = []
    for item in by_product.values():
        prices = [s["weighted_average_unit_price"] for s in item["suppliers"] if s["weighted_average_unit_price"] is not None]
        item["supplier_count"] = len(item["suppliers"])
        item["price_spread"] = round(max(prices) - min(prices), 2) if len(prices) >= 2 else None
        item["lowest_weighted_average_supplier_id"] = (
            min(item["suppliers"], key=lambda s: s["weighted_average_unit_price"])["supplier_id"]
            if item["suppliers"] else None
        )
        products.append(item)
    return {
        "analysis": "supplier_price_intelligence",
        "shop_id": shop_id,
        "product_count": len(products),
        "products": products,
        "limitations": [
            "Uses received purchase invoices only and compares recorded unit prices",
            "Does not normalize taxes, discounts, freight, credit terms or product quality",
            "Different pack sizes or units may not be directly comparable",
            "Historical lowest price is not a promise of current availability",
            "Recommendations do not contact suppliers or place orders",
        ],
    }
