"""Shop-staff read-only endpoints for KiranaAI planning agents."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.routes import require_shop_staff, get_current_user
from app.models.user import User
from app.services.demand_forecast_service import forecast_demand
from app.services.reorder_service import build_reorder_recommendations
from app.agents.supplier_agent import compare_suppliers
from app.agents.orchestrator import route_question
from app.services.inventory_intelligence_service import analyze_inventory, get_dead_stock
from app.services.expiry_intelligence_service import analyze_expiry_risk
from app.services.stockout_prediction_service import predict_stockout_risk
from app.services.event_demand_service import analyze_event_demand
from app.services.supplier_price_intelligence_service import compare_supplier_prices
from app.services.seasonal_demand_service import analyze_seasonal_demand
from app.services.supplier_performance_service import analyze_supplier_performance
from app.services.financial_intelligence_service import analyze_financial_position

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


@router.get("/shops/{shop_id}/agents/seasonal-demand")
def seasonal_demand(
    shop_id: int,
    history_days: int = Query(365, ge=300, le=730),
    limit: int = Query(50, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return analyze_seasonal_demand(db, shop_id, history_days, limit)


@router.get("/shops/{shop_id}/agents/event-demand")
def event_demand(
    shop_id: int,
    event_name: str = Query(..., min_length=1, max_length=100),
    event_start: date = Query(...),
    window_days: int = Query(7, ge=1, le=30),
    baseline_days: int = Query(56, ge=28, le=180),
    limit: int = Query(50, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    try:
        return analyze_event_demand(
            db, shop_id, event_name, event_start, window_days, baseline_days, limit
        )
    except ValueError as error:
        raise HTTPException(422, str(error))


@router.get("/shops/{shop_id}/agents/stockout-risk")
def stockout_risk(
    shop_id: int,
    history_days: int = Query(30, ge=7, le=365),
    lead_time_days: int = Query(7, ge=1, le=90),
    warning_days: int = Query(14, ge=1, le=90),
    limit: int = Query(100, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return predict_stockout_risk(
        db, shop_id, history_days, lead_time_days, warning_days, limit
    )


@router.get("/shops/{shop_id}/agents/dead-stock")
def dead_stock(
    shop_id: int,
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(50, ge=1, le=100),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return get_dead_stock(db, days=days, limit=limit, shop_id=shop_id)


@router.get("/shops/{shop_id}/agents/expiry-risk")
def expiry_risk(
    shop_id: int,
    horizon_days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return analyze_expiry_risk(db, shop_id, horizon_days=horizon_days, limit=limit)


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
    return build_reorder_recommendations(
        db, days, lead_time_days, safety_days, limit, shop_id=shop_id
    )


@router.get("/shops/{shop_id}/agents/supplier-prices")
def supplier_prices(
    shop_id: int,
    limit: int = Query(100, ge=1, le=500),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return compare_supplier_prices(db, shop_id, limit)


@router.get("/shops/{shop_id}/agents/supplier-performance")
def supplier_performance(
    shop_id: int,
    limit: int = Query(100, ge=1, le=500),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return analyze_supplier_performance(db, shop_id, limit)


@router.get("/shops/{shop_id}/agents/financial-position")
def financial_position(
    shop_id: int,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return analyze_financial_position(db, shop_id)


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = payload.get("question")
    try:
        plan = route_question(question)
    except ValueError as error:
        raise HTTPException(400, str(error))

    restricted_agents = []
    if current_user.role != "Owner":
        restricted_agents = [
            agent for agent in plan["agents"] if agent in {"budget", "approval"}
        ]
        plan["agents"] = [
            agent for agent in plan["agents"] if agent not in {"budget", "approval"}
        ]

    results = {}
    for agent in plan["agents"]:
        try:
            if agent == "inventory":
                from app.agents.inventory_agent import understand_inventory_question
                intent = understand_inventory_question(question)
                if intent.intent != "unknown":
                    results["inventory"] = analyze_inventory(
                        db, intent.intent, intent.days, intent.limit, shop_id=shop_id
                    )
            elif agent == "expiry":
                results["expiry"] = analyze_expiry_risk(db, shop_id)
            elif agent == "forecast":
                results["forecast"] = forecast_demand(db, shop_id=shop_id)
            elif agent == "stockout":
                results["stockout"] = predict_stockout_risk(db, shop_id=shop_id)
            elif agent == "seasonal":
                results["seasonal"] = analyze_seasonal_demand(db, shop_id=shop_id)
            elif agent == "event":
                results["event"] = {
                    "status": "requires_event_parameters",
                    "message": "For an event comparison, provide event_name, event_start and window_days to the event-demand endpoint.",
                }
            elif agent == "reorder":
                results["reorder"] = build_reorder_recommendations(db, shop_id=shop_id)
            elif agent == "supplier":
                results["suppliers"] = compare_suppliers(db, shop_id)
                results["supplier_prices"] = compare_supplier_prices(db, shop_id)
                results["supplier_performance"] = analyze_supplier_performance(db, shop_id)
            elif agent == "financial":
                results["financial"] = analyze_financial_position(db, shop_id)
            elif agent == "budget":
                from app.models.shop_purchase_budget import ShopPurchaseBudget
                budget = db.query(ShopPurchaseBudget).filter(
                    ShopPurchaseBudget.shop_id == shop_id
                ).first()
                results["budget"] = (
                    {"available_amount": str(budget.available_amount), "currency": budget.currency}
                    if budget else
                    {"available_amount": "0.00", "currency": "INR", "configured": False}
                )
            elif agent == "sales":
                from app.agents.sales_analytics_agent import (
                    understand_sales_question, format_sales_answer,
                )
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
        except (ValueError, KeyError) as error:
            results[agent] = {
                "status": "insufficient_or_invalid_input",
                "message": str(error),
            }

    return {
        "plan": plan,
        "results": results,
        "restricted_agents": restricted_agents,
        "evidence_summary": {
            "successful_specialists": sorted(results.keys()),
            "specialist_count": len(results),
            "partial": any(
                isinstance(value, dict) and value.get("status") in {
                    "insufficient_or_invalid_input", "requires_event_parameters"
                }
                for value in results.values()
            ),
        },
        "safety": {
            "read_only": True,
            "purchase_orders_created": False,
            "owner_approval_required": True,
        },
    }
