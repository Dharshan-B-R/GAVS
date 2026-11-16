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
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.models.product_alias import ProductAlias
from app.services.product_name_intelligence_service import normalize_product_name, match_product_name
from sqlalchemy.exc import IntegrityError
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement
from app.models.batch_verification import BatchVerification


router = APIRouter(tags=["Shop Operations and Supplier Workspace"])


class SupplierConnectionInput(BaseModel):
    supplier_id: int = Field(gt=0)

class SupplierOrderUpdate(BaseModel):
    status: str = Field(pattern="^(preparing|dispatched|delayed)$")
    note: str | None = Field(default=None, max_length=500)
    expected_delivery_date: date | None = None


class SupplierProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=2000)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    notes: str | None = Field(default=None, max_length=2000)


class ProductAliasInput(BaseModel):
    product_id: int = Field(gt=0)
    alias: str = Field(min_length=1, max_length=180)
    source: str = Field(default="owner", max_length=30)


class ProductNameMatchInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)


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
        "gstin": current_supplier.gstin,
        "notes": current_supplier.notes,
    }


@router.put("/supplier/profile")
def update_supplier_profile(
    payload: SupplierProfileUpdate,
    current_supplier: Supplier = Depends(get_current_distributor),
    db: Session = Depends(get_db),
):
    current_supplier.name = payload.name.strip()
    current_supplier.contact_person = payload.contact_person.strip() if payload.contact_person else None
    current_supplier.phone = payload.phone.strip() if payload.phone else None
    current_supplier.address = payload.address.strip() if payload.address else None
    current_supplier.gstin = payload.gstin.strip().upper() if payload.gstin else None
    current_supplier.notes = payload.notes.strip() if payload.notes else None
    db.commit()
    db.refresh(current_supplier)
    return {
        "supplier_id": current_supplier.id,
        "name": current_supplier.name,
        "contact_person": current_supplier.contact_person,
        "email": current_supplier.email,
        "phone": current_supplier.phone,
        "address": current_supplier.address,
        "gstin": current_supplier.gstin,
        "notes": current_supplier.notes,
    }


@router.get("/supplier/orders")
def supplier_orders(
    current_supplier: Supplier = Depends(get_current_distributor),
    db: Session = Depends(get_db),
):
    rows = db.query(Purchase, Shop).join(
        Shop, Shop.id == Purchase.shop_id
    ).options(joinedload(Purchase.items).joinedload(PurchaseItem.product)).filter(
        Purchase.supplier_id == current_supplier.id,
    ).order_by(Purchase.created_at.desc()).limit(100).all()
    return [{
        "purchase_id": purchase.id,
        "purchase_order_number": purchase.invoice_number,
        "shop_id": shop.id,
        "shop_name": shop.name,
        "status": purchase.status,
        "total_amount": purchase.total_amount,
        "created_at": purchase.created_at,
        "expected_delivery_date": purchase.expected_delivery_date,
        "supplier_status": purchase.supplier_status,
        "supplier_status_note": purchase.supplier_status_note,
        "supplier_updated_at": purchase.supplier_updated_at,
        "items": [{
            "product_id": item.product_id,
            "product_name": item.product.name if item.product else None,
            "unit": item.product.unit if item.product else None,
            "quantity": item.quantity,
            "ordered_quantity": item.ordered_quantity,
            "received_quantity": item.received_quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        } for item in purchase.items],
    } for purchase, shop in rows]



@router.patch("/supplier/orders/{purchase_id}/status")
def update_supplier_order_status(
    purchase_id: int,
    payload: SupplierOrderUpdate,
    current_supplier: Supplier = Depends(get_current_distributor),
    db: Session = Depends(get_db),
):
    """Supplier reports fulfilment progress for its own order, never receipt or stock."""
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.supplier_id == current_supplier.id,
    ).with_for_update().first()
    if purchase is None:
        raise HTTPException(404, "Purchase order not found")
    if purchase.status in {"received", "cancelled"}:
        raise HTTPException(409, "This order can no longer be updated by the supplier")
    if purchase.status not in {"ordered", "confirmed"}:
        raise HTTPException(409, "Only ordered or confirmed orders can be updated")
    purchase.supplier_status = payload.status
    purchase.supplier_status_note = payload.note.strip() if payload.note else None
    if payload.expected_delivery_date is not None:
        purchase.expected_delivery_date = payload.expected_delivery_date
    purchase.supplier_updated_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "purchase_id": purchase.id,
        "supplier_status": purchase.supplier_status,
        "supplier_status_note": purchase.supplier_status_note,
        "expected_delivery_date": purchase.expected_delivery_date,
        "supplier_updated_at": purchase.supplier_updated_at,
    }


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



class OpeningBatchInput(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    expiry_date: date


class ReconcileBatchQuantity(BaseModel):
    batch_id: int = Field(gt=0)
    quantity: float = Field(ge=0)


class ReconcileBatchesInput(BaseModel):
    product_id: int = Field(gt=0)
    batches: list[ReconcileBatchQuantity] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=255)


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
    batches = db.query(ProductBatch).filter(
        ProductBatch.product_id == product.id,
        ProductBatch.quantity > 0,
    ).order_by(ProductBatch.expiry_date.asc(), ProductBatch.id.asc()).with_for_update().all()
    batch_total = sum(float(batch.quantity or 0) for batch in batches)
    if abs(batch_total - before) > 0.000001:
        raise HTTPException(409, "Batch quantities do not match product stock. Reconcile batches before adjusting.")

    if change < 0:
        reduction = abs(change)
        if reduction > before + 0.000001:
            raise HTTPException(409, "Stock reduction exceeds recorded stock")
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



@router.get("/shops/{shop_id}/distributor-directory")
def distributor_directory(
    shop_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    connected_ids = db.query(ShopDistributorConnection.supplier_id).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.is_active.is_(True),
    ).subquery()
    rows = db.query(Supplier).filter(
        Supplier.is_active.is_(True),
        ~Supplier.id.in_(connected_ids),
    ).order_by(Supplier.name.asc()).limit(100).all()
    return [{
        "supplier_id": supplier.id,
        "name": supplier.name,
        "contact_person": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
    } for supplier in rows]


@router.get("/shops/{shop_id}/purchase-orders")
def list_shop_purchase_orders(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    rows = db.query(Purchase).options(joinedload(Purchase.items)).filter(
        Purchase.shop_id == shop_id,
        Purchase.proposal_id.isnot(None),
    ).order_by(Purchase.created_at.desc()).limit(100).all()
    return [{
        "purchase_id": purchase.id,
        "proposal_id": purchase.proposal_id,
        "supplier_id": purchase.supplier_id,
        "purchase_order_number": purchase.invoice_number,
        "status": purchase.status,
        "total_amount": purchase.total_amount,
        "expected_delivery_date": purchase.expected_delivery_date,
        "supplier_status": purchase.supplier_status,
        "supplier_status_note": purchase.supplier_status_note,
        "supplier_updated_at": purchase.supplier_updated_at,
        "supplier_invoice_number": purchase.supplier_invoice_number,
        "invoice_amount": purchase.invoice_amount,
        "received_at": purchase.received_at,
        "items": [{
            "purchase_item_id": item.id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "batch_id": item.batch_id,
        } for item in purchase.items],
    } for purchase in rows]



@router.get("/shops/{shop_id}/inventory/batches")
def list_shop_inventory_batches(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    rows = db.query(ProductBatch, Product).join(
        Product, Product.id == ProductBatch.product_id
    ).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
        ProductBatch.quantity > 0,
    ).order_by(ProductBatch.expiry_date.asc(), Product.name.asc()).limit(500).all()
    return [{
        "batch_id": batch.id,
        "product_id": product.id,
        "product_name": product.name,
        "batch_number": batch.batch_number,
        "quantity": batch.quantity,
        "unit": product.unit,
        "expiry_date": batch.expiry_date,
        "is_verified": batch.is_verified,
    } for batch, product in rows]



@router.post("/shops/{shop_id}/inventory/reconcile-batches")
def reconcile_shop_batches(
    shop_id: int,
    payload: ReconcileBatchesInput,
    current_user: User = Depends(get_current_user),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    """Physically reconcile every batch for one shop product and record verification history."""
    product = db.query(Product).filter(
        Product.id == payload.product_id,
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).with_for_update().first()
    if product is None:
        raise HTTPException(404, "Active product not found in this shop")

    existing = db.query(ProductBatch).filter(
        ProductBatch.product_id == product.id,
    ).order_by(ProductBatch.id.asc()).with_for_update().all()
    submitted = {item.batch_id: item for item in payload.batches}
    expected_ids = {batch.id for batch in existing}
    if len(submitted) != len(payload.batches) or set(submitted) != expected_ids:
        raise HTTPException(400, "Reconciliation must include every existing batch exactly once")
    before = float(product.quantity or 0)
    total = 0.0
    for batch in existing:
        previous = float(batch.quantity or 0)
        verified = float(submitted[batch.id].quantity)
        if not math.isfinite(verified):
            raise HTTPException(422, "Batch quantities must be finite numbers")
        batch.quantity = verified
        batch.is_verified = True
        batch.verified_at = datetime.now(timezone.utc)
        total += verified
        db.add(BatchVerification(
            batch_id=batch.id,
            previous_quantity=previous,
            verified_quantity=verified,
            performed_by=current_user.id,
            reference_type="reconciliation",
            reason=payload.reason.strip(),
            allow_reverification=1,
        ))
    product.quantity = total
    difference = total - before
    if abs(difference) > 0.000001:
        db.add(StockMovement(
            product_id=product.id,
            movement_type="adjustment",
            quantity_change=difference,
            quantity_before=before,
            quantity_after=total,
            reason=payload.reason.strip(),
            performed_by=current_user.id,
            reference_type="batch_reconciliation",
        ))
    db.commit()
    return {
        "product_id": product.id,
        "quantity_before": before,
        "quantity_after": total,
        "quantity_change": difference,
        "batches_reconciled": len(existing),
        "message": "Batch quantities reconciled and physically verified.",
    }



@router.post("/shops/{shop_id}/products/{product_id}/opening-batch", status_code=201)
def create_opening_batch_for_legacy_stock(
    shop_id: int,
    product_id: int,
    payload: OpeningBatchInput,
    current_user: User = Depends(get_current_user),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    """Attach an unverified batch to existing legacy product stock that predates batch tracking."""
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).with_for_update().first()
    if product is None:
        raise HTTPException(404, "Active product not found in this shop")
    quantity = float(product.quantity or 0)
    if quantity <= 0:
        raise HTTPException(409, "There is no positive opening stock to assign to a batch")
    existing = db.query(ProductBatch).filter(
        ProductBatch.product_id == product.id,
    ).count()
    if existing:
        raise HTTPException(409, "This product already has batch records. Use batch reconciliation instead.")
    if payload.expiry_date < date.today():
        raise HTTPException(400, "Opening batch expiry date cannot be in the past")

    batch = ProductBatch(
        product_id=product.id,
        batch_number=payload.batch_number.strip(),
        expiry_date=payload.expiry_date,
        quantity=quantity,
        purchase_price=float(product.purchase_price or 0),
        is_verified=False,
    )
    db.add(batch)
    db.flush()
    db.add(StockMovement(
        product_id=product.id,
        movement_type="adjustment",
        quantity_change=0,
        quantity_before=quantity,
        quantity_after=quantity,
        reason="Opening batch created for legacy stock",
        performed_by=current_user.id,
        reference_type="opening_batch_setup",
    ))
    db.commit()
    return {
        "product_id": product.id,
        "batch_id": batch.id,
        "quantity": quantity,
        "is_verified": False,
        "message": "Opening batch created. Verify its physical quantity before selling.",
    }



@router.get("/shops/{shop_id}/product-aliases")
def list_product_aliases(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    rows = db.query(ProductAlias, Product).join(
        Product, Product.id == ProductAlias.product_id
    ).filter(
        ProductAlias.shop_id == shop_id,
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).order_by(ProductAlias.alias.asc()).all()
    return [{
        "id": alias.id,
        "product_id": product.id,
        "product_name": product.name,
        "alias": alias.alias,
        "normalized_alias": alias.normalized_alias,
        "source": alias.source,
    } for alias, product in rows]


@router.post("/shops/{shop_id}/product-aliases", status_code=201)
def create_product_alias(
    shop_id: int,
    payload: ProductAliasInput,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == payload.product_id,
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).first()
    if product is None:
        raise HTTPException(404, "Active product not found in this shop")
    normalized = normalize_product_name(payload.alias)
    if not normalized:
        raise HTTPException(422, "Alias must contain letters or numbers")
    alias = ProductAlias(
        shop_id=shop_id,
        product_id=product.id,
        alias=payload.alias.strip(),
        normalized_alias=normalized,
        source=payload.source.strip().lower() or "owner",
    )
    db.add(alias)
    try:
        db.commit()
        db.refresh(alias)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This alias is already registered for this shop")
    return {
        "id": alias.id,
        "shop_id": shop_id,
        "product_id": product.id,
        "product_name": product.name,
        "alias": alias.alias,
        "normalized_alias": alias.normalized_alias,
    }


@router.delete("/shops/{shop_id}/product-aliases/{alias_id}")
def delete_product_alias(
    shop_id: int,
    alias_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    alias = db.query(ProductAlias).filter(
        ProductAlias.id == alias_id,
        ProductAlias.shop_id == shop_id,
    ).first()
    if alias is None:
        raise HTTPException(404, "Product alias not found")
    db.delete(alias)
    db.commit()
    return {"deleted": True, "alias_id": alias_id}


@router.post("/shops/{shop_id}/product-name-matches")
def find_product_name_matches(
    shop_id: int,
    payload: ProductNameMatchInput,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).all()
    aliases = db.query(ProductAlias).filter(
        ProductAlias.shop_id == shop_id,
    ).all()
    alias_by_product = {}
    for alias in aliases:
        alias_by_product.setdefault(alias.product_id, []).append(alias.alias)
    candidates = []
    for product in products:
        candidates.append({
            "product_id": product.id,
            "canonical_name": product.name,
            "alias": "",
        })
        candidates.extend({
            "product_id": product.id,
            "canonical_name": product.name,
            "alias": alias,
        } for alias in alias_by_product.get(product.id, []))
    return match_product_name(payload.name, candidates)
