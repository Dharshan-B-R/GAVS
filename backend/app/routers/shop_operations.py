"""Shop operations and supplier workspace APIs with strict tenant scoping."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import date
import math
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth.routes import get_current_user, require_shop_owner, require_shop_staff, get_current_distributor
from app.models.user import User
from app.models.shop import Shop
from app.models.shop_membership import ShopMembership
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.supplier import Supplier
from app.models.sale import Sale
from app.models.purchase import Purchase
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement


router = APIRouter(tags=["Shop Operations and Supplier Workspace"])


class SupplierConnectionInput(BaseModel):
    supplier_id: int = Field(gt=0)


@router.get("/shops/{shop_id}/employees")
def list_shop_employees(
    shop_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    rows = db.query(ShopMembership, User).join(
        User, User.id == ShopMembership.user_id
    ).filter(
        ShopMembership.shop_id == shop_id,
        ShopMembership.role == "Employee",
    ).order_by(User.full_name.asc()).all()
    return [{
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "is_active": membership.is_active and user.is_active,
        "joined_at": membership.created_at,
    } for membership, user in rows]


@router.patch("/shops/{shop_id}/employees/{user_id}/status")
def set_employee_status(
    shop_id: int,
    user_id: int,
    payload: dict,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    active = payload.get("is_active")
    if not isinstance(active, bool):
        raise HTTPException(422, "is_active must be a boolean")
    row = db.query(ShopMembership).filter(
        ShopMembership.shop_id == shop_id,
        ShopMembership.user_id == user_id,
        ShopMembership.role == "Employee",
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Employee membership not found")
    row.is_active = active
    db.commit()
    return {"user_id": user_id, "shop_id": shop_id, "is_active": active}


@router.get("/shops/{shop_id}/distributors")
def list_shop_distributors(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    rows = db.query(ShopDistributorConnection, Supplier).join(
        Supplier, Supplier.id == ShopDistributorConnection.supplier_id
    ).filter(
        ShopDistributorConnection.shop_id == shop_id,
    ).order_by(Supplier.name.asc()).all()
    return [{
        "supplier_id": supplier.id,
        "name": supplier.name,
        "contact_person": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
        "is_active": connection.is_active and supplier.is_active,
    } for connection, supplier in rows]


@router.post("/shops/{shop_id}/distributors", status_code=201)
def connect_distributor(
    shop_id: int,
    payload: SupplierConnectionInput,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    supplier = db.query(Supplier).filter(
        Supplier.id == payload.supplier_id,
        Supplier.is_active.is_(True),
    ).first()
    if supplier is None:
        raise HTTPException(404, "Active supplier not found")
    connection = db.query(ShopDistributorConnection).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.supplier_id == supplier.id,
    ).first()
    if connection is None:
        connection = ShopDistributorConnection(shop_id=shop_id, supplier_id=supplier.id, is_active=True)
        db.add(connection)
    else:
        connection.is_active = True
    db.commit()
    return {"shop_id": shop_id, "supplier_id": supplier.id, "supplier_name": supplier.name, "is_active": True}


@router.delete("/shops/{shop_id}/distributors/{supplier_id}")
def disconnect_distributor(
    shop_id: int,
    supplier_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    connection = db.query(ShopDistributorConnection).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.supplier_id == supplier_id,
    ).first()
    if connection is None:
        raise HTTPException(404, "Distributor connection not found")
    connection.is_active = False
    db.commit()
    return {"shop_id": shop_id, "supplier_id": supplier_id, "is_active": False}


@router.get("/shops/{shop_id}/sales")
def list_shop_sales(
    shop_id: int,
    limit: int = 50,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    rows = db.query(Sale).options(joinedload(Sale.items)).filter(
        Sale.shop_id == shop_id
    ).order_by(Sale.created_at.desc()).limit(limit).all()
    return [{
        "sale_id": sale.id,
        "total_amount": sale.total_amount,
        "discount_amount": sale.discount_amount,
        "payment_method": sale.payment_method,
        "notes": sale.notes,
        "created_at": sale.created_at,
        "items": [{
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        } for item in sale.items],
    } for sale in rows]


@router.get("/supplier/profile")
def supplier_profile(current_supplier: Supplier = Depends(get_current_distributor)):
    return {
        "supplier_id": current_supplier.id,
        "name": current_supplier.name,
        "contact_person": current_supplier.contact_person,
        "email": current_supplier.email,
        "phone": current_supplier.phone,
        "address": current_supplier.address,
    }


@router.get("/supplier/orders")
def supplier_orders(
    current_supplier: Supplier = Depends(get_current_distributor),
    db: Session = Depends(get_db),
):
    rows = db.query(Purchase, Shop).join(
        Shop, Shop.id == Purchase.shop_id
    ).options(joinedload(Purchase.items)).filter(
        Purchase.supplier_id == current_supplier.id,
        Purchase.status.in_(["ordered", "confirmed"]),
    ).order_by(Purchase.created_at.desc()).limit(100).all()
    return [{
        "purchase_id": purchase.id,
        "purchase_order_number": purchase.invoice_number,
        "shop_id": shop.id,
        "shop_name": shop.name,
        "status": purchase.status,
        "total_amount": purchase.total_amount,
        "created_at": purchase.created_at,
        "items": [{
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        } for item in purchase.items],
    } for purchase, shop in rows]


@router.post("/supplier/orders/{purchase_id}/confirm")
def confirm_supplier_order(
    purchase_id: int,
    current_supplier: Supplier = Depends(get_current_distributor),
    db: Session = Depends(get_db),
):
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.supplier_id == current_supplier.id,
    ).with_for_update().first()
    if purchase is None:
        raise HTTPException(404, "Purchase order not found")
    if purchase.status == "confirmed":
        return {"purchase_id": purchase.id, "status": purchase.status, "message": "Order already confirmed"}
    if purchase.status != "ordered":
        raise HTTPException(409, "Only newly placed orders can be confirmed")
    purchase.status = "confirmed"
    db.commit()
    return {"purchase_id": purchase.id, "status": purchase.status, "confirmed_at": datetime.now(timezone.utc)}



class StockAdjustmentInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity_change: float
    reason: str = Field(min_length=3, max_length=255)
    batch_number: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None


@router.post("/shops/{shop_id}/inventory/adjustments", status_code=201)
def adjust_inventory_stock(
    shop_id: int,
    payload: StockAdjustmentInput,
    current_user: User = Depends(get_current_user),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    """Record an audited stock correction while keeping batch totals consistent."""
    change = float(payload.quantity_change)
    if not math.isfinite(change) or abs(change) < 0.000001:
        raise HTTPException(400, "quantity_change must be a finite non-zero number")
    product = db.query(Product).filter(
        Product.id == payload.product_id,
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).with_for_update().first()
    if product is None:
        raise HTTPException(404, "Active product not found in this shop")

    before = float(product.quantity or 0)
    if change < 0:
        reduction = abs(change)
        if reduction > before + 0.000001:
            raise HTTPException(409, "Stock reduction exceeds recorded stock")
        batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product.id,
            ProductBatch.quantity > 0,
        ).order_by(ProductBatch.expiry_date.asc(), ProductBatch.id.asc()).with_for_update().all()
        batch_total = sum(float(batch.quantity or 0) for batch in batches)
        if abs(batch_total - before) > 0.000001:
            raise HTTPException(409, "Batch quantities do not match product stock. Reconcile batches before adjusting.")
        remaining = reduction
        for batch in batches:
            take = min(float(batch.quantity), remaining)
            batch.quantity = float(batch.quantity) - take
            remaining -= take
            if remaining <= 0.000001:
                break
        product.quantity = max(before - reduction, 0)
    else:
        if not payload.batch_number or not payload.batch_number.strip() or payload.expiry_date is None:
            raise HTTPException(422, "Adding stock requires a batch_number and expiry_date")
        if payload.expiry_date < date.today():
            raise HTTPException(400, "Cannot add an already expired batch")
        db.add(ProductBatch(
            product_id=product.id,
            batch_number=payload.batch_number.strip(),
            expiry_date=payload.expiry_date,
            quantity=change,
            purchase_price=float(product.purchase_price or 0),
            is_verified=False,
        ))
        product.quantity = before + change

    movement = StockMovement(
        product_id=product.id,
        movement_type="adjustment",
        quantity_change=change,
        quantity_before=before,
        quantity_after=float(product.quantity),
        reason=payload.reason.strip(),
        performed_by=current_user.id,
        reference_type="manual_adjustment",
    )
    db.add(movement)
    db.commit()
    db.refresh(product)
    return {
        "product_id": product.id,
        "quantity_before": before,
        "quantity_change": change,
        "quantity_after": float(product.quantity),
        "batch_verification_required": change > 0,
        "message": "Stock adjustment recorded with an audit movement.",
    }
