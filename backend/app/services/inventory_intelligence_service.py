"""
Read-only inventory intelligence queries for the KiranaAI Inventory Agent.

The service owns database access and deterministic calculations. It does not
import FastAPI routes, mutate stock, create purchases, or place orders.
Stock coverage always uses verified, unexpired batch quantities.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement

DEFAULT_DAYS = 30
MAX_DAYS = 365
MAX_LIMIT = 100


def _validate(days: int, limit: int = 10) -> None:
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_DAYS}")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


def _sales_subquery(db: Session, days: int):
    """Aggregate negative sale movements into positive units sold per product."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return (
        db.query(
            StockMovement.product_id.label("product_id"),
            func.sum(-StockMovement.quantity_change).label("units_sold"),
        )
        .filter(
            StockMovement.movement_type == "sale",
            StockMovement.quantity_change < 0,
            StockMovement.created_at >= start,
            StockMovement.created_at <= end,
        )
        .group_by(StockMovement.product_id)
        .subquery()
    )


def _saleable_subquery(db: Session):
    """Only verified, unexpired positive batch stock is considered saleable."""
    return (
        db.query(
            ProductBatch.product_id.label("product_id"),
            func.sum(ProductBatch.quantity).label("saleable_stock"),
        )
        .filter(
            ProductBatch.is_verified.is_(True),
            ProductBatch.expiry_date >= date.today(),
            ProductBatch.quantity > 0,
        )
        .group_by(ProductBatch.product_id)
        .subquery()
    )


def get_low_stock(db: Session, limit: int = 10) -> dict[str, Any]:
    """Find active products whose recorded quantity is at/below minimum stock."""
    _validate(DEFAULT_DAYS, limit)
    rows = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            Product.quantity <= Product.minimum_stock,
        )
        .order_by(Product.quantity.asc(), Product.name.asc())
        .limit(limit)
        .all()
    )
    products = [{
        "product_id": p.id,
        "product_name": p.name,
        "current_stock": float(p.quantity or 0),
        "minimum_stock": float(p.minimum_stock or 0),
        "unit": p.unit,
        "shortfall": max(float(p.minimum_stock or 0) - float(p.quantity or 0), 0),
    } for p in rows]
    return {"analysis": "low_stock", "count": len(products), "products": products}


def get_stock_coverage(
    db: Session, days: int = DEFAULT_DAYS, limit: int = 10,
    warning_days: int = 7,
) -> dict[str, Any]:
    """Calculate remaining days from saleable batch stock and sales velocity."""
    _validate(days, limit)
    if not 1 <= warning_days <= 90:
        raise ValueError("warning_days must be between 1 and 90")
    sales, saleable = _sales_subquery(db, days), _saleable_subquery(db)
    rows = (
        db.query(
            Product,
            func.coalesce(saleable.c.saleable_stock, 0).label("saleable_stock"),
            func.coalesce(sales.c.units_sold, 0).label("units_sold"),
        )
        .outerjoin(saleable, Product.id == saleable.c.product_id)
        .outerjoin(sales, Product.id == sales.c.product_id)
        .filter(Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .limit(limit)
        .all()
    )
    products = []
    for product, saleable_qty, units_sold in rows:
        saleable_qty, units_sold = float(saleable_qty or 0), float(units_sold or 0)
        daily = units_sold / days
        coverage = saleable_qty / daily if daily > 0 else None
        if saleable_qty <= 0:
            status = "out_of_stock"
        elif saleable_qty <= float(product.minimum_stock or 0):
            status = "critical"
        elif coverage is None:
            status = "unknown_demand"
        elif coverage <= warning_days:
            status = "low_stock"
        else:
            status = "healthy"
        products.append({
            "product_id": product.id,
            "product_name": product.name,
            "recorded_stock": float(product.quantity or 0),
            "saleable_stock": saleable_qty,
            "minimum_stock": float(product.minimum_stock or 0),
            "unit": product.unit,
            "units_sold": units_sold,
            "average_daily_sales": round(daily, 2),
            "estimated_days_remaining": round(coverage, 2) if coverage is not None else None,
            "stock_status": status,
        })
    return {
        "analysis": "stock_coverage", "analysis_period_days": days,
        "warning_threshold_days": warning_days,
        "count": len(products), "products": products,
    }


def get_dead_stock(db: Session, days: int = 90, limit: int = 10) -> dict[str, Any]:
    """Find mature active products with positive stock and no recorded sales."""
    _validate(days, limit)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sales = _sales_subquery(db, days)
    rows = (
        db.query(Product)
        .outerjoin(sales, Product.id == sales.c.product_id)
        .filter(
            Product.is_active.is_(True), Product.quantity > 0,
            Product.created_at <= cutoff,
            func.coalesce(sales.c.units_sold, 0) == 0,
        )
        .order_by(Product.quantity.desc(), Product.name.asc())
        .limit(limit).all()
    )
    products = [{
        "product_id": p.id, "product_name": p.name,
        "current_stock": float(p.quantity or 0), "unit": p.unit,
        "days_without_recorded_sales": days,
        "estimated_stock_value": round(float(p.quantity or 0) * float(p.purchase_price or 0), 2),
    } for p in rows]
    return {"analysis": "dead_stock", "analysis_period_days": days,
            "count": len(products), "products": products}


def get_movement_products(
    db: Session, movement: str, days: int = DEFAULT_DAYS, limit: int = 10,
) -> dict[str, Any]:
    """Rank mature products with sales; slow-moving means lowest positive sales."""
    _validate(days, limit)
    if movement not in {"fast_moving", "slow_moving"}:
        raise ValueError("movement must be fast_moving or slow_moving")
    cutoff, sales = datetime.now(timezone.utc) - timedelta(days=days), _sales_subquery(db, days)
    query = (
        db.query(Product, func.coalesce(sales.c.units_sold, 0).label("units_sold"))
        .outerjoin(sales, Product.id == sales.c.product_id)
        .filter(Product.is_active.is_(True), Product.created_at <= cutoff,
                 func.coalesce(sales.c.units_sold, 0) > 0)
    )
    ordering = (func.coalesce(sales.c.units_sold, 0).desc()
                if movement == "fast_moving"
                else func.coalesce(sales.c.units_sold, 0).asc())
    rows = query.order_by(ordering, Product.name.asc()).limit(limit).all()
    products = [{
        "product_id": p.id, "product_name": p.name,
        "current_stock": float(p.quantity or 0), "unit": p.unit,
        "units_sold": float(sold or 0),
        "average_daily_sales": round(float(sold or 0) / days, 2),
    } for p, sold in rows]
    return {"analysis": movement, "analysis_period_days": days,
            "count": len(products), "products": products}


def get_expiry_intelligence(
    db: Session, days: int = 60, limit: int = 10,
) -> dict[str, Any]:
    """Return expired and soon-to-expire batches with positive remaining quantity."""
    _validate(days, limit)
    today, horizon = date.today(), date.today() + timedelta(days=days)
    rows = (
        db.query(ProductBatch, Product)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(Product.is_active.is_(True), ProductBatch.quantity > 0,
                ProductBatch.expiry_date <= horizon)
        .order_by(ProductBatch.expiry_date.asc(), Product.name.asc())
        .limit(limit).all()
    )
    batches = []
    for batch, product in rows:
        delta = (batch.expiry_date - today).days
        batches.append({
            "batch_id": batch.id, "product_id": product.id,
            "product_name": product.name, "batch_number": batch.batch_number,
            "quantity": float(batch.quantity or 0), "unit": product.unit,
            "expiry_date": batch.expiry_date.isoformat(),
            "days_to_expiry": delta, "is_expired": delta < 0,
            "is_verified": bool(batch.is_verified),
        })
    return {"analysis": "expiry", "horizon_days": days,
            "count": len(batches), "batches": batches}


def get_data_readiness(db: Session) -> dict[str, Any]:
    """Assess active-product maturity and whether recent sales are recorded."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    total = db.query(func.count(Product.id)).filter(Product.is_active.is_(True)).scalar() or 0
    mature = db.query(func.count(Product.id)).filter(
        Product.is_active.is_(True), Product.created_at <= cutoff
    ).scalar() or 0
    sales_filter = (
        Product.is_active.is_(True), StockMovement.movement_type == "sale",
        StockMovement.quantity_change < 0, StockMovement.created_at >= cutoff,
    )
    with_sales = db.query(func.count(func.distinct(StockMovement.product_id))).join(
        Product, Product.id == StockMovement.product_id
    ).filter(*sales_filter).scalar() or 0
    units = db.query(func.coalesce(func.sum(-StockMovement.quantity_change), 0)).join(
        Product, Product.id == StockMovement.product_id
    ).filter(*sales_filter).scalar() or 0
    if mature == 0:
        status, message = "insufficient_history", "No active products have completed 30 days of history."
    elif float(units) == 0:
        status, message = "sales_tracking_needs_validation", (
            "Mature products exist, but no sales were recorded in the last 30 days. "
            "Validate sales recording before relying on movement analysis."
        )
    else:
        status, message = "ready_for_initial_detection", (
            "Product age and recent sales data are available for initial analysis. "
            "Validate sales coverage before decisions."
        )
    return {
        "analysis": "data_readiness", "analysis_period_days": 30,
        "summary": {
            "total_active_products": int(total), "mature_products": int(mature),
            "new_products": max(int(total) - int(mature), 0),
            "products_with_sales": int(with_sales),
            "products_without_sales": max(int(total) - int(with_sales), 0),
            "total_units_sold": float(units),
        },
        "readiness": {"status": status, "message": message},
    }


def get_inventory_health(db: Session, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Summarize saleable-stock status and expiry/data-readiness indicators."""
    _validate(days, MAX_LIMIT)
    coverage = get_stock_coverage(db, days=days, limit=MAX_LIMIT)
    expiry = get_expiry_intelligence(db, days=60, limit=MAX_LIMIT)
    readiness = get_data_readiness(db)
    statuses = [p["stock_status"] for p in coverage["products"]]
    return {
        "analysis": "inventory_health", "analysis_period_days": days,
        "summary": {
            "total_products_analysed": len(statuses),
            "out_of_stock_products": statuses.count("out_of_stock"),
            "critical_stock_products": statuses.count("critical"),
            "low_stock_products": statuses.count("low_stock"),
            "healthy_products": statuses.count("healthy"),
            "unknown_demand_products": statuses.count("unknown_demand"),
            "expired_or_expiring_batches": expiry["count"],
        },
        "data_readiness": readiness["readiness"],
    }


def analyze_inventory(
    db: Session, intent: str, days: int = DEFAULT_DAYS, limit: int = 10,
) -> dict[str, Any]:
    """Route a supported agent intent to its deterministic read-only analysis."""
    if intent == "low_stock":
        return get_low_stock(db, limit)
    if intent == "stock_coverage":
        return get_stock_coverage(db, days, limit)
    if intent == "dead_stock":
        return get_dead_stock(db, days, limit)
    if intent in {"fast_moving", "slow_moving"}:
        return get_movement_products(db, intent, days, limit)
    if intent == "expiry":
        return get_expiry_intelligence(db, days, limit)
    if intent == "data_readiness":
        return get_data_readiness(db)
    if intent == "inventory_health":
        return get_inventory_health(db, days)
    raise ValueError(f"Unsupported inventory intent: {intent}")
