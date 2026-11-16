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
from app.models.supplier import Supplier
from app.models.supplier_issue import SupplierIssue
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.purchase import Purchase
from app.services.inventory_intelligence_service import _saleable_subquery
from app.services.event_demand_service import analyze_event_demand

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


@router.put("/shops/{shop_id}/customers/{customer_id}/assign")
def assign_legacy_customer_to_shop(shop_id: int, customer_id: int,
                                   membership=Depends(require_shop_owner),
                                   db: Session = Depends(get_db)):
    """Explicitly assign an unowned legacy customer and its existing khata history."""
    customer = db.query(Customer).filter(Customer.id == customer_id).with_for_update().first()
    if customer is None:
        raise HTTPException(404, "Customer not found")
    if customer.shop_id == shop_id:
        return {"customer_id": customer_id, "shop_id": shop_id, "message": "Customer is already assigned to this shop."}
    if customer.shop_id is not None:
        raise HTTPException(409, "Customer already belongs to another shop and cannot be reassigned through this endpoint.")
    customer.shop_id = shop_id
    db.commit()
    return {"customer_id": customer_id, "shop_id": shop_id,
            "message": "Legacy customer and their khata history are now attributed to this shop by owner action."}


@router.get("/shops/{shop_id}/agents/event-demand/{event_id}")
def compare_saved_festival_event(shop_id: int, event_id: int,
                                 window_days: int = Query(7, ge=1, le=30),
                                 baseline_days: int = Query(56, ge=28, le=180),
                                 limit: int = Query(50, ge=1, le=100),
                                 membership=Depends(require_shop_staff),
                                 db: Session = Depends(get_db)):
    event = db.query(FestivalEvent).filter(
        FestivalEvent.id == event_id, FestivalEvent.shop_id == shop_id,
        FestivalEvent.is_active.is_(True),
    ).first()
    if event is None:
        raise HTTPException(404, "Active festival event not found")
    try:
        return analyze_event_demand(
            db, shop_id, event.name, event.event_date,
            window_days=window_days, baseline_days=baseline_days, limit=limit,
        )
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get("/shops/{shop_id}/availability-snapshots")
def list_availability_snapshot_coverage(shop_id: int,
                                        start_date: date | None = None,
                                        end_date: date | None = None,
                                        membership=Depends(require_shop_staff),
                                        db: Session = Depends(get_db)):
    query = db.query(InventoryAvailabilitySnapshot).filter(
        InventoryAvailabilitySnapshot.shop_id == shop_id
    )
    if start_date:
        query = query.filter(InventoryAvailabilitySnapshot.snapshot_date >= start_date)
    if end_date:
        query = query.filter(InventoryAvailabilitySnapshot.snapshot_date <= end_date)
    rows = query.order_by(InventoryAvailabilitySnapshot.snapshot_date.desc()).limit(1000).all()
    days = {}
    for row in rows:
        item = days.setdefault(str(row.snapshot_date), {"product_count": 0, "available_count": 0, "out_of_stock_count": 0})
        item["product_count"] += 1
        item["available_count"] += int(row.is_available)
        item["out_of_stock_count"] += int(not row.is_available)
    return {"shop_id": shop_id, "days": [{"date": day, **value} for day, value in sorted(days.items(), reverse=True)]}


@router.post("/shops/{shop_id}/supplier-issues", status_code=201)
def create_supplier_issue(shop_id: int, payload: dict = Body(...),
                          membership=Depends(require_shop_staff),
                          current_user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    try:
        supplier_id = int(payload.get("supplier_id"))
    except (TypeError, ValueError):
        raise HTTPException(422, "supplier_id is required")
    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.is_active.is_(True)
    ).first()
    connection = db.query(ShopDistributorConnection).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.supplier_id == supplier_id,
        ShopDistributorConnection.is_active.is_(True),
    ).first()
    if supplier is None or connection is None:
        raise HTTPException(404, "Active supplier connection not found for this shop")
    purchase_id = payload.get("purchase_id")
    if purchase_id is not None:
        try:
            purchase_id = int(purchase_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "purchase_id must be an integer")
        purchase = db.query(Purchase).filter(
            Purchase.id == purchase_id, Purchase.shop_id == shop_id,
            Purchase.supplier_id == supplier_id,
        ).first()
        if purchase is None:
            raise HTTPException(404, "Purchase order not found for this shop and supplier")
    issue_type = str(payload.get("issue_type") or "").strip().lower()
    description = str(payload.get("description") or "").strip()
    severity = str(payload.get("severity") or "medium").strip().lower()
    if not issue_type or len(issue_type) > 50 or not description or len(description) > 2000:
        raise HTTPException(422, "issue_type and description are required")
    if severity not in {"low", "medium", "high", "critical"}:
        raise HTTPException(422, "severity must be low, medium, high or critical")
    issue = SupplierIssue(
        shop_id=shop_id, supplier_id=supplier_id, purchase_id=purchase_id,
        issue_type=issue_type, description=description, severity=severity,
        created_by_user_id=current_user.id,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return {"issue_id": issue.id, "supplier_id": supplier_id,
            "purchase_id": purchase_id, "status": issue.status}


@router.get("/shops/{shop_id}/supplier-issues")
def list_supplier_issues(shop_id: int, supplier_id: int | None = None,
                         status: str | None = None, limit: int = Query(100, ge=1, le=500),
                         membership=Depends(require_shop_staff), db: Session = Depends(get_db)):
    query = db.query(SupplierIssue).filter(SupplierIssue.shop_id == shop_id)
    if supplier_id is not None:
        query = query.filter(SupplierIssue.supplier_id == supplier_id)
    if status is not None:
        if status not in {"open", "resolved"}:
            raise HTTPException(422, "status must be open or resolved")
        query = query.filter(SupplierIssue.status == status)
    rows = query.order_by(SupplierIssue.created_at.desc()).limit(limit).all()
    return [{"issue_id": issue.id, "supplier_id": issue.supplier_id,
             "purchase_id": issue.purchase_id, "issue_type": issue.issue_type,
             "description": issue.description, "severity": issue.severity,
             "status": issue.status, "created_at": issue.created_at,
             "resolved_at": issue.resolved_at} for issue in rows]


@router.patch("/shops/{shop_id}/supplier-issues/{issue_id}/resolve")
def resolve_supplier_issue(shop_id: int, issue_id: int,
                           membership=Depends(require_shop_staff),
                           db: Session = Depends(get_db)):
    issue = db.query(SupplierIssue).filter(
        SupplierIssue.id == issue_id, SupplierIssue.shop_id == shop_id
    ).with_for_update().first()
    if issue is None:
        raise HTTPException(404, "Supplier issue not found")
    if issue.status == "resolved":
        return {"issue_id": issue_id, "status": "resolved", "resolved_at": issue.resolved_at}
    from datetime import datetime, timezone
    issue.status = "resolved"
    issue.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"issue_id": issue_id, "status": issue.status, "resolved_at": issue.resolved_at}
