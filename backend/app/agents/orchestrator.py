"""KiranaAI specialist routing. This module plans work; it never mutates stock or orders."""
import re

SUPPORTED = {
    "inventory": ("stock", "inventory", "expiry", "dead stock", "low stock"),
    "sales": ("sales", "revenue", "best selling", "top selling"),
    "forecast": ("forecast", "demand", "next month", "next 30 days"),
    "reorder": ("reorder", "restock", "what should i buy", "purchase recommendation"),
    "supplier": ("supplier", "distributor"),
    "budget": ("budget", "cash available", "purchase budget"),
    "approval": ("approve", "purchase proposal", "pending order"),
}


def route_question(question: str) -> dict:
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("Question must contain 1-1000 characters")
    normalized = re.sub(r"\s+", " ", question.lower()).strip()
    matches = [agent for agent, terms in SUPPORTED.items() if any(term in normalized for term in terms)]
    if not matches:
        return {"intent": "clarification", "agents": [], "question": question}
    return {"intent": "multi_agent" if len(matches) > 1 else matches[0],
            "agents": matches, "question": question}
