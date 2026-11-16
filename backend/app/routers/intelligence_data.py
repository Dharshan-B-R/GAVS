"""Shop-scoped data capture for financial, supplier and local-demand intelligence."""
from datetime import date
from math import isfinite

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.routes import get_current_user, require_shop_owner, require_shop_staff
from app.database import get_db
from app.models.customer import Customer
from app.models.festival_event import FestivalEvent
from app.models.inventory_availability_snapshot import InventoryAvailabilitySnapshot
from app.models.khata_transaction import KhataTransaction
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.services.inventory_intelligence_service import _saleable_subquery

router = APIRouter(tags=["KiranaAI Intelligence Data"])


@router.post("/shops/{shop_id}/customers", status_code=201)
def create_shop_customer(shop_id: int, payload: dict = Body(...),
                         membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 150:
        raise HTTPException(422, "Customer name must contain 1-150 characters")
    customer = Customer(
        shop_id=shop_id, name=name,
        phone=(str(payload["phone"]).strip()[:15] if payload.get("phone") else None),
        address=(str(payload["address"]).strip()[:300] if payload.get("address") else None),
        notes=(str(payload["notes"]).strip()[:500] if payload.get("notes") else None),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {"customer_id": customer.id, "shop_id": shop_id, "name": customer.name}


@router.get("/shops/{shop_id}/customers")
def list_shop_customers(shop_id: int, limit: int = Query(100, ge=1, le=500),
                        membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    rows = db.query(Customer).filter(
        Customer.shop_id == shop_id, Customer.is_active.is_(True)
    ).order_by(Customer.name.asc()).limit(limit).all()
    return [{"customer_id": c.id, "name": c.name, "phone": c.phone} for c in rows]


@router.post("/shops/{shop_id}/customers/{customer_id}/khata", status_code=201)
def add_shop_khata_transaction(shop_id: int, customer_id: int, payload: dict = Body(...),
                               membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.shop_id == shop_id,
        Customer.is_active.is_(True),
    ).with_for_update().first()
    if customer is None:
        raise HTTPException(404, "Shop customer not found")
    kind = payload.get("transaction_type")
    if kind not in {"credit", "repayment"}:
        raise HTTPException(422, "transaction_type must be credit or repayment")
    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(422, "A valid positive amount is required")
    if not isfinite(amount) or amount <= 0 or amount > 100000000:
        raise HTTPException(422, "Amount must be positive and within the supported limit")
    balance_query = db.query(KhataTransaction).filter(KhataTransaction.customer_id == customer_id)
    credits = sum(float(x[0] or 0) for x in balance_query.with_entities(KhataTransaction.amount).filter(KhataTransaction.transaction_type == "credit").all())
    repayments = sum(float(x[0] or 0) for x in balance_query.with_entities(KhataTransaction.amount).filter(KhataTransaction.transaction_type == "repayment").all())
    outstanding = round(credits - repayments, 2)
    if kind == "repayment" and amount > outstanding + 0.0001:
        raise HTTPException(409, {"message": "Repayment exceeds outstanding balance", "outstanding_amount": outstanding})
    transaction = KhataTransaction(
        customer_id=customer_id, transaction_type=kind, amount=amount,
        description=(str(payload.get("description") or "").strip()[:300] or None),
        reference_number=(str(payload.get("reference_number") or "").strip()[:100] or None),
        performed_by=str(getattr(membership, "user_id", "") or "") or None,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return {"transaction_id": transaction.id, "customer_id": customer_id,
            "transaction_type": kind, "amount": round(amount, 2),
            "outstanding_amount": round(outstanding + amount if kind == "credit" else outstanding - amount, 2)}


@router.get("/shops/{shop_id}/customers/{customer_id}/khata")
def get_shop_khata_ledger(shop_id: int, customer_id: int,
                          membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.shop_id == shop_id
    ).first()
    if customer is None:
        raise HTTPException(404, "Shop customer not found")
    rows = db.query(KhataTransaction).filter(
        KhataTransaction.customer_id == customer_id
    ).order_by(KhataTransaction.created_at.asc(), KhataTransaction.id.asc()).all()
    balance = 0.0
    ledger = []
    for row in rows:
        amount = float(row.amount)
        balance += amount if row.transaction_type == "credit" else -amount
        ledger.append({
            "transaction_id": row.id, "transaction_type": row.transaction_type,
            "amount": round(amount, 2), "description": row.description,
            "created_at": row.created_at, "running_balance": round(balance, 2),
        })
    return {"customer_id": customer.id, "customer_name": customer.name,
            "outstanding_amount": round(balance, 2), "transactions": ledger}


@router.put("/shops/{shop_id}/intelligence-settings")
def update_intelligence_settings(shop_id: int, payload: dict = Body(...),
                                  membership=Depends(require_shop_owner), db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if shop is None:
        raise HTTPException(404, "Shop not found")
    allowed = {"city": 100, "state": 100, "country": 100, "timezone": 64}
    for field, max_length in allowed.items():
        if field in payload:
            value = str(payload[field]).strip()
            if not value or len(value) > max_length:
                raise HTTPException(422, f"{field} must contain 1-{max_length} characters")
            setattr(shop, field, value)
    db.commit()
    return {"shop_id": shop_id, "city": shop.city, "state": shop.state,
            "country": shop.country, "timezone": shop.timezone}


@router.post("/shops/{shop_id}/festival-calendar", status_code=201)
def add_festival_event(shop_id: int, payload: dict = Body(...),
                       membership=Depends(require_shop_owner),
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    name = str(payload.get("name") or "").strip()
    try:
        event_date = date.fromisoformat(str(payload.get("event_date")))
    except (TypeError, ValueError):
        raise HTTPException(422, "event_date must use YYYY-MM-DD")
    event_type = str(payload.get("event_type") or "festival").strip().lower()
    if not name or len(name) > 120 or event_type not in {"festival", "local_event", "promotion", "market_day"}:
        raise HTTPException(422, "Provide a valid event name and event_type")
    event = FestivalEvent(
        shop_id=shop_id, name=name, event_date=event_date, event_type=event_type,
        notes=(str(payload.get("notes") or "").strip()[:500] or None),
        created_by_user_id=current_user.id,
    )
    db.add(event)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "An event with this name and date already exists for this shop")
    db.refresh(event)
    return {"event_id": event.id, "name": event.name, "event_date": event.event_date,
            "event_type": event.event_type, "shop_id": shop_id}


@router.get("/shops/{shop_id}/festival-calendar")
def get_festival_calendar(shop_id: int, start_date: date | None = None,
                          end_date: date | None = None,
                          membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    query = db.query(FestivalEvent).filter(
        FestivalEvent.shop_id == shop_id, FestivalEvent.is_active.is_(True)
    )
    if start_date:
        query = query.filter(FestivalEvent.event_date >= start_date)
    if end_date:
        query = query.filter(FestivalEvent.event_date <= end_date)
    rows = query.order_by(FestivalEvent.event_date.asc()).limit(250).all()
    return [{"event_id": e.id, "name": e.name, "event_date": e.event_date,
             "event_type": e.event_type, "notes": e.notes} for e in rows]


@router.delete("/shops/{shop_id}/festival-calendar/{event_id}")
def deactivate_festival_event(shop_id: int, event_id: int,
                              membership=Depends(require_shop_owner), db: Session = Depends(get_db)):
    event = db.query(FestivalEvent).filter(
        FestivalEvent.id == event_id, FestivalEvent.shop_id == shop_id
    ).first()
    if event is None:
        raise HTTPException(404, "Festival event not found")
    event.is_active = False
    db.commit()
    return {"event_id": event_id, "active": False}


@router.post("/shops/{shop_id}/availability-snapshots/capture")
def capture_daily_availability(shop_id: int, snapshot_date: date | None = None,
                                membership=Depends(require_shop_staff),
                                current_user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    day = snapshot_date or date.today()
    products = db.query(Product).filter(
        Product.shop_id == shop_id, Product.is_active.is_(True)
    ).all()
    saleable = _saleable_subquery(db, shop_id)
    captured = 0
    for product in products:
        qty = db.query(saleable.c.saleable_stock).filter(
            saleable.c.product_id == product.id
        ).scalar()
        available_qty = max(float(qty or 0), 0.0)
        row = db.query(InventoryAvailabilitySnapshot).filter(
            InventoryAvailabilitySnapshot.shop_id == shop_id,
            InventoryAvailabilitySnapshot.product_id == product.id,
            InventoryAvailabilitySnapshot.snapshot_date == day,
        ).first()
        if row is None:
            row = InventoryAvailabilitySnapshot(
                shop_id=shop_id, product_id=product.id, snapshot_date=day,
                available_quantity=available_qty, is_available=available_qty > 0,
                captured_by_user_id=current_user.id,
            )
            db.add(row)
        else:
            row.available_quantity = available_qty
            row.is_available = available_qty > 0
            row.captured_by_user_id = current_user.id
        captured += 1
    db.commit()
    return {"shop_id": shop_id, "snapshot_date": day, "products_captured": captured,
            "message": "Saleable batch availability recorded for this date."}
