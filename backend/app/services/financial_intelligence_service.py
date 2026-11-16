"""Read-only financial position from shop-owned ledgers.

Customer khata is not joined until Customer can be safely attributed to a shop.
This avoids leaking or blending balances between shops.
"""
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.purchase import Purchase
from app.models.purchase_payment import PurchasePayment


def analyze_financial_position(db: Session, shop_id: int) -> dict:
    purchases = db.query(Purchase).filter(
        Purchase.shop_id == shop_id,
        Purchase.status == "received",
    ).order_by(Purchase.purchase_date.desc()).limit(500).all()

    invoices = []
    total_invoiced = Decimal("0.00")
    total_paid = Decimal("0.00")
    for purchase in purchases:
        paid_value = db.query(func.coalesce(func.sum(PurchasePayment.amount), 0)).filter(
            PurchasePayment.purchase_id == purchase.id
        ).scalar()
        invoice_value = Decimal(str(purchase.total_amount or 0))
        paid = Decimal(str(paid_value or 0))
        outstanding = max(invoice_value - paid, Decimal("0.00"))
        total_invoiced += invoice_value
        total_paid += min(invoice_value, paid)
        if outstanding > 0:
            invoices.append({
                "purchase_id": purchase.id,
                "supplier_id": purchase.supplier_id,
                "invoice_number": purchase.invoice_number,
                "invoice_amount": str(invoice_value.quantize(Decimal("0.01"))),
                "recorded_paid_amount": str(paid.quantize(Decimal("0.01"))),
                "outstanding_amount": str(outstanding.quantize(Decimal("0.01"))),
                "purchase_date": purchase.purchase_date,
            })

    return {
        "analysis": "financial_position",
        "shop_id": shop_id,
        "receivables": {
            "status": "unavailable",
            "reason": "Customer records and khata transactions do not currently contain shop ownership. Aggregating them would risk exposing balances across shops.",
        },
        "payables": {
            "status": "available",
            "outstanding_amount": str(max(total_invoiced - total_paid, Decimal("0.00")).quantize(Decimal("0.01"))),
            "currency": "INR",
            "open_invoice_count": len(invoices),
            "invoices": invoices[:100],
            "basis": "received purchase invoice amount minus recorded purchase payments",
        },
        "limitations": [
            "Khata receivables remain unavailable until customers are shop-scoped",
            "Supplier payable ageing is approximate because invoices have no contractual due dates",
            "Cash balance and bank/UPI settlement data are not present in these tables",
        ],
    }
}