"""Shop-scoped khata and supplier payable intelligence.

These aggregates expose receivables and recorded purchase obligations. The
current schema stores transaction dates but no per-entry due dates, so ageing
uses time since the original credit transaction and is labelled approximate.
Supplier payable is based on received invoices less recorded payments.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.khata_transaction import KhataTransaction
from app.models.purchase import Purchase
from app.models.purchase_payment import PurchasePayment


def analyze_financial_position(db: Session, shop_id: int) -> dict:
    # Khata tables currently do not carry shop_id. Join Customer only after the
    # customer ownership column exists; never aggregate across shops by guess.
    if not hasattr(Customer, "shop_id"):
        return {
            "analysis": "financial_position",
            "shop_id": shop_id,
            "receivables": {"status": "unavailable", "reason": "Customer records are not shop-scoped in the current schema; cross-shop balances are intentionally not exposed."},
            "payables": _supplier_payables(db, shop_id),
            "limitations": [
                "Customer khata cannot be safely attributed to a shop until a customer ownership/membership relationship is added",
                "Khata records have no due date; ageing cannot be calculated reliably",
                "Supplier payable uses recorded received purchases and payments only",
            ],
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    credits = db.query(
        KhataTransaction.customer_id,
        func.sum(
            func.case(
                (KhataTransaction.transaction_type == "credit", KhataTransaction.amount),
                else_=0,
            )
        ).label("credited"),
        func.sum(
            func.case(
                (KhataTransaction.transaction_type == "repayment", KhataTransaction.amount),
                else_=0,
            )
        ).label("repaid"),
        func.min(KhataTransaction.created_at).label("oldest_transaction"),
    ).join(Customer, Customer.id == KhataTransaction.customer_id).filter(
        Customer.shop_id == shop_id,
        Customer.is_active.is_(True),
    ).group_by(KhataTransaction.customer_id).all()

    open_balances = []
    total_receivable = Decimal("0")
    for row in credits:
        balance = Decimal(str(row.credited or 0)) - Decimal(str(row.repaid or 0))
        if balance <= 0:
            continue
        total_receivable += balance
        age_days = None
        oldest = row.oldest_transaction
        if oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            age_days = max((datetime.now(timezone.utc) - oldest).days, 0)
        open_balances.append({
            "customer_id": row.customer_id,
            "outstanding_amount": str(balance.quantize(Decimal("0.01"))),
            "days_since_oldest_transaction": age_days,
            "ageing_status": "approximate_oldest_transaction_age",
        })

    return {
        "analysis": "financial_position",
        "shop_id": shop_id,
        "receivables": {
            "status": "available",
            "outstanding_amount": str(total_receivable.quantize(Decimal("0.01"))),
            "customer_count": len(open_balances),
            "customers": open_balances[:100],
            "ageing_basis": "oldest khata transaction, not contractual due date",
        },
        "payables": _supplier_payables(db, shop_id),
        "limitations": [
            "Receivable ageing is approximate because khata transactions have no due dates",
            "No cash balance or bank/UPI settlement data is stored in these tables",
            "Supplier payables include only received purchase invoices and recorded payments",
        ],
    }


def _supplier_payables(db: Session, shop_id: int) -> dict:
    rows = db.query(Purchase).filter(
        Purchase.shop_id == shop_id,
        Purchase.status == "received",
    ).order_by(Purchase.purchase_date.desc()).limit(500).all()
    entries = []
    total_invoiced = Decimal("0")
    total_paid = Decimal("0")
    for purchase in rows:
        paid = db.query(func.coalesce(func.sum(PurchasePayment.amount), 0)).filter(
            PurchasePayment.purchase_id == purchase.id
        ).scalar()
        invoice = Decimal(str(purchase.total_amount or 0))
        paid_amount = Decimal(str(paid or 0))
        due = max(invoice - paid_amount, Decimal("0"))
        total_invoiced += invoice
        total_paid += min(invoice, paid_amount)
        if due > 0:
            entries.append({
                "purchase_id": purchase.id,
                "supplier_id": purchase.supplier_id,
                "invoice_number": purchase.invoice_number,
                "invoice_amount": str(invoice.quantize(Decimal("0.01"))),
                "recorded_paid_amount": str(paid_amount.quantize(Decimal("0.01"))),
                "outstanding_amount": str(due.quantize(Decimal("0.01"))),
                "purchase_date": purchase.purchase_date,
            })
    return {
        "status": "available",
        "outstanding_amount": str(max(total_invoiced - total_paid, Decimal("0")).quantize(Decimal("0.01"))),
        "currency": "INR",
        "open_invoice_count": len(entries),
        "invoices": entries[:100],
        "basis": "received purchase invoice total minus recorded purchase payments",
    }
