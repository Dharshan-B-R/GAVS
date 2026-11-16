"""KiranaAI specialist intent routing; planning only, no side effects."""
import re

SUPPORTED = {
    "expiry": ("expiry", "expiring", "expired", "spoilage"),
    "inventory": ("stock", "inventory", "dead stock", "low stock", "slow moving", "fast moving"),
    "sales": ("sales", "revenue", "best selling", "top selling"),
    "forecast": ("forecast", "demand", "next month", "next 30 days"),
    "stockout": ("stockout", "run out", "running out", "stock-out"),
    "seasonal": ("seasonal", "seasonality", "monthly demand pattern", "festival", "festive"),
    "event": ("festival", "festive", "event demand", "during diwali", "during pongal", "during sankranti"),
    "reorder": ("reorder", "restock", "what should i buy", "purchase recommendation", "purchase plan"),
    "supplier": ("supplier", "distributor", "vendor"),
    "financial": ("khata", "udhar", "receivable", "payable", "working capital", "financial position"),
    "budget": ("budget", "cash available", "purchase budget"),
    "approval": ("approve", "purchase proposal", "pending order"),
}


def route_question(question: str) -> dict:
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("Question must contain 1-1000 characters")
    normalized = re.sub(r"\s+", " ", question.lower()).strip()
    matches = [
        agent for agent, terms in SUPPORTED.items()
        if any(term in normalized for term in terms)
    ]
    if "event" in matches and "seasonal" not in matches:
        matches.insert(matches.index("event"), "seasonal")
    if not matches:
        return {
            "intent": "clarification", "agents": [], "question": question,
            "clarification": (
                "Ask about expiry, dead stock, stockout risk, sales, demand forecast, "
                "seasonality, festival comparisons, reorder planning, suppliers or finances."
            ),
        }
    return {
        "intent": "multi_agent" if len(matches) > 1 else matches[0],
        "agents": matches, "question": question,
    }
}