"""Shop-staff read-only endpoints for KiranaAI planning agents."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.routes import require_shop_staff
from app.services.demand_forecast_service import forecast_demand
from app.services.reorder_service import build_reorder_recommendations
from app.agents.supplier_agent import compare_suppliers
from app.agents.orchestrator import route_question
from app.services.inventory_intelligence_service import analyze_inventory

router = APIRouter(tags=["KiranaAI Agents"])


@router.get("/shops/{shop_id}/agents/forecast")
def demand_forecast(
    shop_id: int,
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(50, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return forecast_demand(db, days, limit, shop_id=shop_id)


@router.get("/shops/{shop_id}/agents/reorder-recommendations")
def reorder_recommendations(
    shop_id: int,
    days: int = Query(30, ge=7, le=365),
    lead_time_days: int = Query(7, ge=1, le=90),
    safety_days: int = Query(3, ge=0, le=60),
    limit: int = Query(50, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return build_reorder_recommendations(db, days, lead_time_days, safety_days, limit, shop_id=shop_id)


@router.get("/shops/{shop_id}/agents/suppliers")
def supplier_comparison(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return compare_suppliers(db, shop_id)


@router.post("/shops/{shop_id}/agents/orchestrate")
def orchestrate_question(
    shop_id: int,
    payload: dict,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    question = payload.get("question")
    try:
        plan = route_question(question)
    except ValueError as error:
        raise HTTPException(400, str(error))
    results = {}
    for agent in plan["agents"]:
        if agent == "inventory":
            # Existing inventory analytics are read-only; no purchase side effects.
            from app.agents.inventory_agent import understand_inventory_question
            intent = understand_inventory_question(question)
            if intent.intent != "unknown":
                results["inventory"] = analyze_inventory(db, intent.intent, intent.days, intent.limit, shop_id=shop_id)
        elif agent == "forecast":
            results["forecast"] = forecast_demand(db, shop_id=shop_id)
        elif agent == "reorder":
            results["reorder"] = build_reorder_recommendations(db, shop_id=shop_id)
        elif agent == "supplier":
            results["suppliers"] = compare_suppliers(db, shop_id)
        elif agent == "budget":
            from app.models.shop_purchase_budget import ShopPurchaseBudget
            budget = db.query(ShopPurchaseBudget).filter(ShopPurchaseBudget.shop_id == shop_id).first()
            results["budget"] = {"available_amount": str(budget.available_amount), "currency": budget.currency} if budget else {"available_amount": "0.00", "currency": "INR", "configured": False}
        elif agent == "sales":
            from app.agents.sales_analytics_agent import understand_sales_question, format_sales_answer
            from app.services.sales_intelligence_service import analyze_sales
            sales_intent = understand_sales_question(question)
            if sales_intent.intent == "unknown":
                results["sales"] = {
                    "intent": "unknown",
                    "answer": sales_intent.clarification or
                              "Ask about sales summary, daily sales, or best-selling products.",
                    "analytics_data": None,
                }
            else:
                sales_data = analyze_sales(
                    db=db, shop_id=shop_id, intent=sales_intent.intent,
                    days=sales_intent.days, limit=sales_intent.limit,
                )
                results["sales"] = {
                    "intent": sales_intent.intent,
                    "answer": format_sales_answer(
                        question=question, intent=sales_intent.intent,
                        analytics_data=sales_data,
                    ),
                    "analytics_data": sales_data,
                }
        elif agent == "approval":
            from app.models.purchase_proposal import PurchaseProposal
            pending = db.query(PurchaseProposal).filter(
                PurchaseProposal.shop_id == shop_id,
                PurchaseProposal.status == "pending",
            ).order_by(PurchaseProposal.created_at.desc()).limit(20).all()
            results["approval"] = {
                "pending_count": len(pending),
                "proposals": [
                    {"proposal_id": p.id, "total_amount": str(p.total_amount),
                     "items": p.items, "created_at": p.created_at}
                    for p in pending
                ],
            }
    return {"plan": plan, "results": results,
            "safety": {"read_only": True, "purchase_orders_created": False,
                       "owner_approval_required": True}}
