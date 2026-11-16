"""Owner-controlled shop budgets and purchase proposal approval API.

Approval records intent only. It deliberately does not create a Purchase,
PurchaseItem, ProductBatch, payment, or stock movement.
"""
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.routes import get_current_user, require_shop_owner, require_shop_staff
from app.models.user import User
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.models.purchase_proposal import PurchaseProposal
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement


router = APIRouter(tags=["Purchase Planning and Approval"])
CENT = Decimal("0.01")


class BudgetUpdate(BaseModel):
    available_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class ProposalItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class ProposalCreate(BaseModel):
    supplier_id: Optional[int] = Field(default=None, gt=0)
    items: list[ProposalItemInput] = Field(min_length=1, max_length=100)
    rationale: Optional[str] = Field(default=None, max_length=1000)


class ProposalDecision(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


class PurchaseReceiptItem(BaseModel):
    purchase_item_id: int = Field(gt=0)
    batch_number: str = Field(min_length=1, max_length=100)
    expiry_date: date


class PurchaseReceiptCreate(BaseModel):
    items: list[PurchaseReceiptItem] = Field(min_length=1, max_length=100)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@router.put("/shops/{shop_id}/purchase-budget")
def set_purchase_budget(
    shop_id: int,
    payload: BudgetUpdate,
    membership=Depends(require_shop_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    currency = payload.currency.upper()
    if currency != "INR":
        raise HTTPException(400, "Only INR budgets are currently supported")
    budget = db.query(ShopPurchaseBudget).filter(
        ShopPurchaseBudget.shop_id == shop_id
    ).with_for_update().first()
    committed_rows = db.query(PurchaseProposal.total_amount).filter(
        PurchaseProposal.shop_id == shop_id,
        PurchaseProposal.status.in_(["approved", "ordered"]),
    ).all()
    committed_amount = sum((row[0] for row in committed_rows), Decimal("0.00"))
    if payload.available_amount < committed_amount:
        raise HTTPException(
            409,
            detail={
                "message": "Budget cannot be reduced below already approved or ordered proposals",
                "committed_amount": str(committed_amount),
            },
        )
    if budget is None:
        budget = ShopPurchaseBudget(
            shop_id=shop_id,
            available_amount=_money(payload.available_amount),
            currency=currency,
            updated_by_user_id=current_user.id,
        )
        db.add(budget)
    else:
        budget.available_amount = _money(payload.available_amount)
        budget.currency = currency
        budget.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(budget)
    return {
        "shop_id": shop_id,
        "available_amount": str(budget.available_amount),
        "currency": budget.currency,
        "updated_at": budget.updated_at,
    }


@router.get("/shops/{shop_id}/purchase-budget")
def get_purchase_budget(
    shop_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    budget = db.query(ShopPurchaseBudget).filter(
        ShopPurchaseBudget.shop_id == shop_id
    ).first()
    available = Decimal("0.00") if budget is None else Decimal(budget.available_amount)
    committed_rows = db.query(PurchaseProposal.total_amount).filter(
        PurchaseProposal.shop_id == shop_id,
        PurchaseProposal.status.in_(["approved", "ordered"]),
    ).all()
    committed = sum((Decimal(row[0]) for row in committed_rows), Decimal("0.00"))
    return {
        "shop_id": shop_id,
        "available_amount": str(available),
        "committed_amount": str(committed),
        "remaining_amount": str(max(available - committed, Decimal("0.00"))),
        "currency": "INR" if budget is None else budget.currency,
        "updated_at": None if budget is None else budget.updated_at,
    }


@router.post("/shops/{shop_id}/purchase-proposals", status_code=201)
def create_purchase_proposal(
    shop_id: int,
    payload: ProposalCreate,
    membership=Depends(require_shop_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budget = db.query(ShopPurchaseBudget).filter(
        ShopPurchaseBudget.shop_id == shop_id
    ).first()
    if budget is None:
        raise HTTPException(409, "Set the shop purchase budget before creating proposals")

    if payload.supplier_id is not None:
        supplier = db.query(Supplier).filter(
            Supplier.id == payload.supplier_id,
            Supplier.is_active.is_(True),
        ).first()
        if supplier is None:
            raise HTTPException(404, "Active supplier not found")
        connection = db.query(ShopDistributorConnection).filter(
            ShopDistributorConnection.shop_id == shop_id,
            ShopDistributorConnection.supplier_id == payload.supplier_id,
            ShopDistributorConnection.is_active.is_(True),
        ).first()
        if connection is None:
            raise HTTPException(409, "Supplier is not actively connected to this shop")

    product_ids = [item.product_id for item in payload.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(400, "A product may appear only once in a proposal")
    products = db.query(Product).filter(
        Product.id.in_(product_ids),
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
    ).all()
    if len(products) != len(product_ids):
        raise HTTPException(404, "One or more active products were not found")

    item_snapshots = []
    total = Decimal("0.00")
    for item in payload.items:
        subtotal = _money(item.quantity * item.unit_price)
        total += subtotal
        product = next(p for p in products if p.id == item.product_id)
        item_snapshots.append({
            "product_id": item.product_id,
            "product_name": product.name,
            "quantity": str(item.quantity),
            "unit": product.unit,
            "unit_price": str(_money(item.unit_price)),
            "subtotal": str(subtotal),
        })
    total = _money(total)

    proposal = PurchaseProposal(
        shop_id=shop_id,
        supplier_id=payload.supplier_id,
        created_by_user_id=current_user.id,
        status="pending",
        total_amount=total,
        budget_at_creation=budget.available_amount,
        items=item_snapshots,
        rationale=payload.rationale,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "shop_id": shop_id,
        "status": proposal.status,
        "total_amount": str(proposal.total_amount),
        "budget_at_creation": str(proposal.budget_at_creation),
        "items": proposal.items,
        "message": "Proposal created. It has not been ordered and no stock was changed.",
    }


@router.get("/shops/{shop_id}/purchase-proposals")
def list_purchase_proposals(
    shop_id: int,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    proposals = db.query(PurchaseProposal).filter(
        PurchaseProposal.shop_id == shop_id
    ).order_by(PurchaseProposal.created_at.desc()).limit(100).all()
    return [{
        "proposal_id": p.id,
        "status": p.status,
        "total_amount": str(p.total_amount),
        "items": p.items,
        "rationale": p.rationale,
        "decision_note": p.decision_note,
        "created_at": p.created_at,
        "decided_at": p.decided_at,
    } for p in proposals]


@router.post("/shops/{shop_id}/purchase-proposals/{proposal_id}/decision")
def decide_purchase_proposal(
    shop_id: int,
    proposal_id: int,
    payload: ProposalDecision,
    membership=Depends(require_shop_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal = db.query(PurchaseProposal).filter(
        PurchaseProposal.id == proposal_id,
        PurchaseProposal.shop_id == shop_id,
    ).with_for_update().first()
    if proposal is None:
        raise HTTPException(404, "Purchase proposal not found")
    if proposal.status != "pending":
        raise HTTPException(409, f"Proposal is already {proposal.status}")

    if payload.approve:
        budget = db.query(ShopPurchaseBudget).filter(
            ShopPurchaseBudget.shop_id == shop_id
        ).with_for_update().first()
        if budget is None:
            raise HTTPException(409, "Shop purchase budget is not configured")
        # Reserve budget already committed to other approved or ordered
        # proposals. Locking the budget row serializes owner approvals per shop.
        committed_rows = db.query(PurchaseProposal.total_amount).filter(
            PurchaseProposal.shop_id == shop_id,
            PurchaseProposal.status.in_(["approved", "ordered"]),
        ).all()
        committed_amount = sum((row[0] for row in committed_rows), Decimal("0.00"))
        remaining_budget = budget.available_amount - committed_amount
        if proposal.total_amount > remaining_budget:
            raise HTTPException(
                409,
                detail={
                    "message": "Proposal exceeds the remaining uncommitted cash budget",
                    "proposal_total": str(proposal.total_amount),
                    "committed_amount": str(committed_amount),
                    "remaining_budget": str(remaining_budget),
                },
            )
        proposal.status = "approved"
    else:
        proposal.status = "rejected"

    proposal.decided_by_user_id = current_user.id
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decision_note = payload.note
    db.commit()
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "decided_by_user_id": proposal.decided_by_user_id,
        "decided_at": proposal.decided_at,
        "message": (
            "Proposal approved. This is not a placed order."
            if payload.approve else "Proposal rejected. No order was placed."
        ),
    }


@router.post("/shops/{shop_id}/purchase-proposals/{proposal_id}/execute")
def execute_approved_purchase_order(
    shop_id: int,
    proposal_id: int,
    membership=Depends(require_shop_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create one internal PO from an approved proposal; never receive stock here."""
    proposal = db.query(PurchaseProposal).filter(
        PurchaseProposal.id == proposal_id,
        PurchaseProposal.shop_id == shop_id,
    ).with_for_update().first()
    if proposal is None:
        raise HTTPException(404, "Purchase proposal not found")

    # A retry after a successful request returns the same PO instead of
    # creating a duplicate purchase or duplicating the committed amount.
    existing = db.query(Purchase).filter(Purchase.proposal_id == proposal.id).first()
    if existing is not None:
        return {
            "proposal_id": proposal.id, "purchase_id": existing.id,
            "status": proposal.status, "purchase_status": existing.status,
            "message": "This proposal already has a purchase order.",
        }
    if proposal.status != "approved":
        raise HTTPException(409, "Only an owner-approved proposal can be executed")
    if proposal.supplier_id is None:
        raise HTTPException(409, "Select a connected supplier before approving and executing this proposal")

    connection = db.query(ShopDistributorConnection).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.supplier_id == proposal.supplier_id,
        ShopDistributorConnection.is_active.is_(True),
    ).first()
    supplier = db.query(Supplier).filter(
        Supplier.id == proposal.supplier_id, Supplier.is_active.is_(True)
    ).first()
    if connection is None or supplier is None:
        raise HTTPException(409, "The proposal supplier is no longer active and connected to this shop")

    snapshots = proposal.items or []
    product_ids = [int(item["product_id"]) for item in snapshots]
    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
        Product.id.in_(product_ids),
    ).all()
    if len(products) != len(set(product_ids)):
        raise HTTPException(409, "A proposed product is no longer active in this shop")
    product_by_id = {product.id: product for product in products}

    purchase = Purchase(
        shop_id=shop_id,
        proposal_id=proposal.id,
        supplier_id=proposal.supplier_id,
        invoice_number=f"KIRANAAI-PO-{proposal.id}",
        total_amount=float(proposal.total_amount),
        payment_status="pending",
        status="ordered",
        notes=f"Created from owner-approved KiranaAI proposal #{proposal.id}",
    )
    db.add(purchase)
    db.flush()

    for item in snapshots:
        product_id = int(item["product_id"])
        product = product_by_id[product_id]
        db.add(PurchaseItem(
            purchase_id=purchase.id,
            product_id=product_id,
            quantity=float(item["quantity"]),
            ordered_quantity=float(item["quantity"]),
            received_quantity=0,
            unit_price=float(item["unit_price"]),
            subtotal=float(item["subtotal"]),
        ))

    proposal.status = "ordered"
    proposal.decision_note = (
        (proposal.decision_note + " | ") if proposal.decision_note else ""
    ) + f"Internal PO {purchase.invoice_number} created by user {current_user.id}"
    db.commit()
    db.refresh(purchase)
    return {
        "proposal_id": proposal.id,
        "purchase_id": purchase.id,
        "purchase_order_number": purchase.invoice_number,
        "status": proposal.status,
        "purchase_status": purchase.status,
        "total_amount": str(proposal.total_amount),
        "message": "Internal purchase order created. Stock was not increased; record goods receipt separately when delivered.",
    }



@router.post("/shops/{shop_id}/purchases/{purchase_id}/receive")
def receive_approved_purchase_order(
    shop_id: int,
    purchase_id: int,
    payload: PurchaseReceiptCreate,
    membership=Depends(require_shop_staff),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive every line of an internal PO once, creating dated batches and stock movements."""
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id,
        Purchase.shop_id == shop_id,
    ).with_for_update().first()
    if purchase is None:
        raise HTTPException(404, "Purchase order not found")
    if purchase.status == "received":
        return {"purchase_id": purchase.id, "status": "received", "message": "Goods for this purchase order were already received"}
    if purchase.status not in {"ordered", "confirmed"}:
        raise HTTPException(409, "Only ordered or supplier-confirmed purchase orders can be received")

    order_items = db.query(PurchaseItem).filter(
        PurchaseItem.purchase_id == purchase.id
    ).order_by(PurchaseItem.id.asc()).with_for_update().all()
    submitted = {item.purchase_item_id: item for item in payload.items}
    expected_ids = {item.id for item in order_items}
    if len(submitted) != len(payload.items) or set(submitted) != expected_ids:
        raise HTTPException(400, "Provide exactly one batch number and expiry date for every purchase-order line")
    today = date.today()
    for order_item in order_items:
        receipt = submitted[order_item.id]
        if receipt.expiry_date < today:
            raise HTTPException(400, f"Batch for purchase item {order_item.id} is already expired")
        if order_item.batch_id is not None:
            raise HTTPException(409, f"Purchase item {order_item.id} already has a received batch")
        product = db.query(Product).filter(
            Product.id == order_item.product_id,
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
        ).with_for_update().first()
        if product is None:
            raise HTTPException(409, "A purchase-order product is no longer active in this shop")
        before = float(product.quantity or 0)
        received_quantity = float(order_item.quantity)
        batch = ProductBatch(
            product_id=product.id,
            batch_number=receipt.batch_number.strip(),
            manufacturing_date=None,
            expiry_date=receipt.expiry_date,
            quantity=received_quantity,
            purchase_price=float(order_item.unit_price),
            is_verified=False,
        )
        db.add(batch)
        db.flush()
        product.quantity = before + received_quantity
        movement = StockMovement(
            product_id=product.id,
            movement_type="purchase",
            quantity_change=received_quantity,
            quantity_before=before,
            quantity_after=product.quantity,
            reason=f"Goods received against PO {purchase.invoice_number}",
            performed_by=current_user.id,
            reference_type="purchase",
            reference_id=purchase.id,
        )
        db.add(movement)
        order_item.batch_id = batch.id

    purchase.status = "received"
    purchase.received_at = datetime.now(timezone.utc)
    purchase.purchase_date = purchase.received_at
    for order_item in order_items:
        order_item.received_quantity = float(order_item.quantity)
        if order_item.ordered_quantity is None:
            order_item.ordered_quantity = float(order_item.quantity)
    db.commit()
    return {
        "purchase_id": purchase.id,
        "status": purchase.status,
        "received_lines": len(order_items),
        "message": "Goods receipt recorded. New batches remain unverified until the shop's batch-verification workflow approves them.",
    }


@router.put("/shops/{shop_id}/purchases/{purchase_id}/expected-delivery")
def set_expected_delivery_date(
    shop_id: int,
    purchase_id: int,
    payload: dict,
    membership=Depends(require_shop_owner),
    db: Session = Depends(get_db),
):
    """Owner records the supplier-promised date used for on-time delivery metrics."""
    raw_date = payload.get("expected_delivery_date")
    try:
        expected = date.fromisoformat(str(raw_date))
    except (TypeError, ValueError):
        raise HTTPException(422, "expected_delivery_date must use YYYY-MM-DD")
    purchase = db.query(Purchase).filter(
        Purchase.id == purchase_id, Purchase.shop_id == shop_id,
    ).with_for_update().first()
    if purchase is None:
        raise HTTPException(404, "Purchase order not found")
    if purchase.status not in {"ordered", "confirmed"}:
        raise HTTPException(409, "Expected delivery date can only be set before goods are received")
    purchase.expected_delivery_date = expected
    db.commit()
    return {
        "purchase_id": purchase.id,
        "expected_delivery_date": purchase.expected_delivery_date,
        "message": "Supplier-promised delivery date recorded.",
    }
