"""Shop-scoped khata receivables and supplier payable intelligence.

Legacy customers with NULL shop_id are excluded until an owner explicitly assigns
them. Khata ageing is approximate because the ledger has no contractual due date.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.khata_transaction import KhataTransaction
from app.models.purchase import Purchase
from app.models.purchase_payment import PurchasePayment


def analyze_financial_position(db: Session, shop_id: int) -> dict:
    customer_rows = db.query(Customer).filter(
        Customer.shop_id == shop_id, Customer.is_active.is_(True)
    ).order_by(Customer.name.asc()).all()
    receivables = []
    total_receivable = Decimal("0.00")
    for customer in customer_rows:
        tx = db.query(KhataTransaction).filter(
            KhataTransaction.customer_id == customer.id
        ).order_by(KhataTransaction.created_at.asc()).all()
        credits = sum((Decimal(str(row.amount)) for row in tx if row.transaction_type == "credit"), Decimal("0.00"))
        repayments = sum((Decimal(str(row.amount)) for row in tx if row.transaction_type == "repayment"), Decimal("0.00"))
        balance = credits - repayments
        if balance <= 0:
            continue
        oldest = tx[0].created_at if tx else None
        age_days = None
        if oldest:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            age_days = max((datetime.now(timezone.utc) - oldest).days, 0)
        total_receivable += balance
        receivables.append({
            "customer_id": customer.id,
            "customer_name": customer.name,
            "outstanding_amount": str(balance.quantize(Decimal("0.01"))),
            "days_since_oldest_transaction": age_days,
            "ageing_basis": "approximate_oldest_transaction_age",
        })

    purchases = db.query(Purchase).filter(
        Purchase.shop_id == shop_id, Purchase.status.in_(["received", "partially_received"])
    ).order_by(Purchase.purchase_date.desc()).limit(500).all()
    invoices = []
    total_invoiced = Decimal("0.00")
    total_paid = Decimal("0.00")
    unverified_purchase_orders = 0
    for purchase in purchases:
        if purchase.proposal_id is not None and purchase.invoice_amount is None:
            unverified_purchase_orders += 1
            continue
        paid_value = db.query(func.coalesce(func.sum(PurchasePayment.amount), 0)).filter(
            PurchasePayment.purchase_id == purchase.id
        ).scalar()
        invoice_value = Decimal(str(
            purchase.invoice_amount if purchase.invoice_amount is not None else purchase.total_amount or 0
        ))
        paid = Decimal(str(paid_value or 0))
        outstanding = max(invoice_value - paid, Decimal("0.00"))
        total_invoiced += invoice_value
        total_paid += min(invoice_value, paid)
        if outstanding > 0:
            invoices.append({
                "purchase_id": purchase.id,
                "supplier_id": purchase.supplier_id,
                "invoice_number": purchase.supplier_invoice_number or purchase.invoice_number,
                "invoice_amount": str(invoice_value.quantize(Decimal("0.01"))),
                "recorded_paid_amount": str(paid.quantize(Decimal("0.01"))),
                "outstanding_amount": str(outstanding.quantize(Decimal("0.01"))),
                "purchase_date": purchase.purchase_date,
                "expected_delivery_date": purchase.expected_delivery_date,
                "received_at": purchase.received_at,
            })

    return {
        "analysis": "financial_position",
        "shop_id": shop_id,
        "receivables": {
            "status": "available",
            "outstanding_amount": str(total_receivable.quantize(Decimal("0.01"))),
            "customer_count": len(receivables),
            "customers": receivables[:100],
            "ageing_basis": "oldest recorded khata transaction, not contractual due date",
            "unassigned_legacy_customer_count": db.query(func.count(Customer.id)).filter(
                Customer.shop_id.is_(None), Customer.is_active.is_(True)
            ).scalar(),
        },
        "payables": {
            "status": "available",
            "outstanding_amount": str(max(total_invoiced - total_paid, Decimal("0.00")).quantize(Decimal("0.01"))),
            "currency": "INR",
            "open_invoice_count": len(invoices),
            "unverified_received_purchase_order_count": unverified_purchase_orders,
            "invoices": invoices[:100],
            "basis": "received purchase invoice amount minus recorded purchase payments",
        },
        "limitations": [
            "Legacy customers without an explicit shop assignment are excluded",
            "Khata ageing is approximate because individual due dates are not stored",
            "Cash balance and bank/UPI settlement data are not present in these tables",
            "Internal purchase orders are excluded from payables until an actual invoice number and invoice amount are captured",
            "Supplier payables include recorded invoice amounts and recorded payments only",
        ],
    }
