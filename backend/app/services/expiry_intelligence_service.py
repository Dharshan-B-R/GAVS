"""Expiry and expiry-loss intelligence based on recorded batches and actions.

This service is deliberately deterministic: it reports recorded exposure and loss,
not speculative spoilage or sales that might have occurred.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expiry_record import ExpiryRecord
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.shop import Shop


def analyze_expiry_risk(
    db: Session,
    shop_id: int,
    horizon_days: int = 30,
    limit: int = 100,
    as_of: date | None = None,
) -> dict:
    if not 1 <= horizon_days <= 365:
        raise ValueError("Expiry horizon must be between 1 and 365 days")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    if as_of is None:
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        try:
            today = datetime.now(ZoneInfo(shop.timezone if shop and shop.timezone else "Asia/Kolkata")).date()
        except ZoneInfoNotFoundError:
            today = date.today()
    else:
        today = as_of
    horizon = today + timedelta(days=horizon_days)
    rows = (
        db.query(ProductBatch, Product)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            ProductBatch.quantity > 0,
            ProductBatch.expiry_date <= horizon,
        )
        .order_by(ProductBatch.expiry_date.asc(), Product.name.asc())
        .all()
    )

    batches = []
    total_at_risk_quantity = 0.0
    estimated_cost_exposure = 0.0
    for batch, product in rows:
        days_remaining = (batch.expiry_date - today).days
        quantity = float(batch.quantity or 0)
        unit_cost = float(batch.purchase_price or 0)
        exposure = quantity * unit_cost
        total_at_risk_quantity += quantity
        estimated_cost_exposure += exposure
        if len(batches) < limit:
            batches.append({
                "batch_id": batch.id,
                "product_id": product.id,
                "product_name": product.name,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date.isoformat(),
                "days_to_expiry": days_remaining,
                "quantity": round(quantity, 3),
                "unit": product.unit,
                "unit_cost": round(unit_cost, 2),
                "estimated_cost_exposure": round(exposure, 2),
                "is_verified": bool(batch.is_verified),
                "status": "expired" if days_remaining < 0 else (
                    "expires_today" if days_remaining == 0 else "expiring_soon"
                ),
                "action_hint": (
                    "Review immediately; batch is past its expiry date"
                    if days_remaining < 0 else
                    "Prioritize sale, supplier return, or approved disposal review"
                ),
            })

    # Only completed, owner-approved disposals count as realized loss.
    # Pending requests reserve stock but are not completed losses. Supplier
    # returns recover inventory and are tracked separately as recorded credits.
    disposal_rows = (
        db.query(
            func.coalesce(func.sum(ExpiryRecord.quantity * ProductBatch.purchase_price), 0),
            func.count(ExpiryRecord.id),
        )
        .join(ProductBatch, ProductBatch.id == ExpiryRecord.batch_id)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            ExpiryRecord.action == "disposal",
            ExpiryRecord.approval_status == "approved",
            ExpiryRecord.action_status == "completed",
        )
        .one()
    )
    credit_total = (
        db.query(func.coalesce(func.sum(ExpiryRecord.credit_amount), 0))
        .join(ProductBatch, ProductBatch.id == ExpiryRecord.batch_id)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
            ExpiryRecord.action == "supplier_return",
            ExpiryRecord.action_status == "completed",
            ExpiryRecord.return_status == "credited",
            ExpiryRecord.credit_amount.isnot(None),
        )
        .scalar()
    )
    recorded_gross_loss = float(disposal_rows[0] or 0)
    recorded_supplier_credits = float(credit_total or 0)

    return {
        "analysis": "expiry_risk",
        "shop_id": shop_id,
        "as_of": today.isoformat(),
        "horizon_days": horizon_days,
        "batch_count": len(rows),
        "at_risk_batch_count": len(rows),
        "returned_batch_count": len(batches),
        "total_at_risk_quantity": round(total_at_risk_quantity, 3),
        "estimated_cost_exposure": round(estimated_cost_exposure, 2),
        "recorded_expiry_action_count": int(disposal_rows[1] or 0),
        "recorded_gross_expiry_loss": round(recorded_gross_loss, 2),
        "recorded_supplier_credits": round(recorded_supplier_credits, 2),
        "recorded_net_expiry_loss": round(max(0.0, recorded_gross_loss - recorded_supplier_credits), 2),
        "currency": "INR",
        "batches": batches,
        "limitations": [
            "Exposure is current batch quantity multiplied by recorded batch purchase price",
            "Recorded losses use expiry action quantities and batch purchase prices",
            "Supplier credits are deducted only when recorded",
            "No unrecorded wastage, markdown sales, or future demand is inferred",
            "Results include only active products belonging to the requested shop",
        ],
    }
