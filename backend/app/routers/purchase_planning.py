"""Owner-controlled shop budgets and purchase proposal approval API.

Approval records intent only. It deliberately does not create a Purchase,
PurchaseItem, ProductBatch, payment, or stock movement.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.routes import get_current_user, require_shop_owner
from app.models.user import User
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.models.purchase_proposal import PurchaseProposal
from app.models.product import Product
from app.models.supplier import Supplier


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
    if budget is None:
        return {"shop_id": shop_id, "available_amount": "0.00", "currency": "INR"}
    return {
        "shop_id": shop_id,
        "available_amount": str(budget.available_amount),
        "currency": budget.currency,
        "updated_at": budget.updated_at,
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

    product_ids = [item.product_id for item in payload.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(400, "A product may appear only once in a proposal")
    products = db.query(Product).filter(
        Product.id.in_(product_ids),
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
        if proposal.total_amount > budget.available_amount:
            raise HTTPException(
                409,
                detail={
                    "message": "Proposal exceeds the current available cash budget",
                    "proposal_total": str(proposal.total_amount),
                    "available_budget": str(budget.available_amount),
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
