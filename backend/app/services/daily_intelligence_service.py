"""Deterministic daily intelligence digest and deduplicated shop alerts."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.intelligence_alert import IntelligenceAlert
from app.models.intelligence_daily_summary import IntelligenceDailySummary
from app.models.shop import Shop
from app.services.expiry_intelligence_service import analyze_expiry_risk
from app.services.stockout_prediction_service import predict_stockout_risk
from app.services.inventory_intelligence_service import get_dead_stock
from app.services.reorder_service import build_reorder_recommendations


def _upsert_alert(db: Session, shop_id: int, *, product_id: int | None,
                  alert_type: str, dedupe_key: str, severity: str,
                  title: str, message: str, now: datetime) -> IntelligenceAlert:
    row = db.query(IntelligenceAlert).filter(
        IntelligenceAlert.shop_id == shop_id,
        IntelligenceAlert.dedupe_key == dedupe_key,
    ).with_for_update().first()
    if row is None:
        row = IntelligenceAlert(
            shop_id=shop_id, product_id=product_id, alert_type=alert_type,
            dedupe_key=dedupe_key, severity=severity, title=title,
            message=message, status="open", first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
    else:
        row.product_id = product_id
        row.severity = severity
        row.title = title
        row.message = message
        row.last_seen_at = now
        if row.status == "resolved":
            row.status = "open"
            row.acknowledged_at = None
    return row


def generate_daily_intelligence_summary(db: Session, shop_id: int) -> dict:
    shop = db.query(Shop).filter(Shop.id == shop_id, Shop.is_active.is_(True)).first()
    if shop is None:
        raise ValueError("Active shop not found")
    local_tz = ZoneInfo(shop.timezone or "Asia/Kolkata")
    now = datetime.now(timezone.utc)
    summary_date = now.astimezone(local_tz).date()

    expiry = analyze_expiry_risk(db, shop_id, horizon_days=30, limit=100)
    stockout = predict_stockout_risk(
        db, shop_id, history_days=30, lead_time_days=7,
        warning_days=14, limit=100,
    )
    dead_stock = get_dead_stock(db, days=90, limit=100, shop_id=shop_id)
    reorder = build_reorder_recommendations(
        db, days=30, lead_time_days=7, safety_days=3, limit=50, shop_id=shop_id,
    )

    seen = 0
    for batch in expiry.get("batches", []):
        status = batch.get("status")
        if status not in {"expired", "expiring_soon", "expires_today"}:
            continue
        days_left = int(batch.get("days_to_expiry") or 0)
        severity = "critical" if status in {"expired", "expires_today"} else (
            "high" if days_left <= 7 else "warning"
        )
        _upsert_alert(
            db, shop_id, product_id=batch.get("product_id"),
            alert_type="expiry", dedupe_key=f"expiry:{batch.get('batch_id')}",
            severity=severity,
            title=f"{batch.get('product_name', 'Product')} batch expiry",
            message=(
                f"Batch {batch.get('batch_number')} has {batch.get('quantity')} "
                f"{batch.get('unit')} remaining; expiry date {batch.get('expiry_date')}."
            ),
            now=now,
        )
        seen += 1

    for product in stockout.get("products", []):
        risk = product.get("risk")
        if risk not in {"stockout", "before_lead_time", "within_warning_window"}:
            continue
        severity = "critical" if risk == "stockout" else "high" if risk == "before_lead_time" else "warning"
        _upsert_alert(
            db, shop_id, product_id=product.get("product_id"),
            alert_type="stockout", dedupe_key=f"stockout:{product.get('product_id')}",
            severity=severity,
            title=f"{product.get('product_name', 'Product')} stockout risk",
            message=(
                f"Risk: {risk}; saleable stock {product.get('saleable_stock')}; "
                f"estimated days remaining {product.get('estimated_days_remaining')}."
            ),
            now=now,
        )
        seen += 1

    for product in dead_stock.get("products", []):
        _upsert_alert(
            db, shop_id, product_id=product.get("product_id"),
            alert_type="dead_stock", dedupe_key=f"dead-stock:{product.get('product_id')}",
            severity="info",
            title=f"{product.get('product_name', 'Product')} may be dead stock",
            message=(
                f"{product.get('current_stock')} {product.get('unit')} remain with no "
                f"recorded sales in the last {product.get('days_without_recorded_sales')} days."
            ),
            now=now,
        )
        seen += 1

    payload = {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "summary_date": summary_date.isoformat(),
        "timezone": shop.timezone,
        "expiry": {
            "at_risk_batch_count": expiry.get("at_risk_batch_count", 0),
            "estimated_cost_exposure": expiry.get("estimated_cost_exposure", 0),
            "recorded_net_expiry_loss": expiry.get("recorded_net_expiry_loss", 0),
            "top_batches": expiry.get("batches", [])[:10],
        },
        "stockout": {
            "summary": stockout.get("summary", {}),
            "top_products": stockout.get("products", [])[:10],
        },
        "dead_stock": {
            "count": dead_stock.get("count", 0),
            "products": dead_stock.get("products", [])[:10],
        },
        "reorder": {
            "recommendation_count": reorder.get("recommendation_count", 0),
            "deferred_count": reorder.get("deferred_count", 0),
            "budget": reorder.get("budget", {}),
            "recommendations": reorder.get("recommendations", [])[:10],
        },
        "alerts_seen_or_refreshed": seen,
        "limitations": [
            "Based on recorded transactions and current verified saleable batches",
            "Availability snapshots improve lost-demand estimates only after sufficient daily coverage",
            "Festival effects are not automatically uplifted",
            "Alerts are decision support; purchase execution still requires owner approval",
        ],
    }

    summary = db.query(IntelligenceDailySummary).filter(
        IntelligenceDailySummary.shop_id == shop_id,
        IntelligenceDailySummary.summary_date == summary_date,
    ).with_for_update().first()
    if summary is None:
        summary = IntelligenceDailySummary(
            shop_id=shop_id, summary_date=summary_date, payload=payload,
        )
        db.add(summary)
    else:
        summary.payload = payload
    db.commit()
    return payload


def generate_all_daily_summaries(db: Session) -> dict:
    shops = db.query(Shop).filter(Shop.is_active.is_(True)).order_by(Shop.id.asc()).all()
    generated = []
    failed = []
    for shop in shops:
        try:
            payload = generate_daily_intelligence_summary(db, shop.id)
            generated.append({"shop_id": shop.id, "summary_date": payload["summary_date"]})
        except Exception as error:
            db.rollback()
            failed.append({"shop_id": shop.id, "error": str(error)})
    return {"generated": generated, "failed": failed}
