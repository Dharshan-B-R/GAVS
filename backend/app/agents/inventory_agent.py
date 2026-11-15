"""
KiranaAI Inventory Agent
========================

Purpose:
    Understand natural-language inventory questions and convert them into
    a small, validated set of inventory-analysis intents.

Design:
    1. Use deterministic Python patterns for common kirana-shop questions.
    2. Use Gemini only when the local rules cannot confidently classify a
       non-empty question.
    3. Return structured intent data; never invent stock quantities, sales,
       expiry dates, or recommendations.
    4. Keep this module independent of FastAPI routes and database models.
       A separate service layer will retrieve trusted inventory data later.

This first version is read-only. It does not update stock, create purchases,
or place orders.
"""

import os
import re
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator


# Load backend environment variables when this module is imported.
load_dotenv()


# Keep the model setting consistent with the existing Sales Analytics Agent.
GEMINI_MODEL = "gemini-3.8-flash"

# Prevent unexpectedly expensive or ambiguous LLM requests.
MAX_QUESTION_LENGTH = 1000
MAX_ANALYSIS_DAYS = 365
MAX_RESULT_LIMIT = 100


class InventoryIntent(BaseModel):
    """
    Validated interpretation of an inventory-related question.

    The API/service layer will use these fields to choose the appropriate
    inventory calculation. The agent itself does not query or mutate data.
    """

    intent: Literal[
        "low_stock",
        "stock_coverage",
        "dead_stock",
        "fast_moving",
        "slow_moving",
        "expiry",
        "data_readiness",
        "inventory_health",
        "unknown",
    ]

    # The period is used by movement-based analyses. Inventory services may
    # apply intent-specific defaults where the underlying endpoint requires it.
    days: int = Field(default=30, ge=1, le=MAX_ANALYSIS_DAYS)

    # Used by ranked lists such as fast-moving or dead-stock products.
    limit: int = Field(default=10, ge=1, le=MAX_RESULT_LIMIT)

    # Optional clarification returned when the question cannot be classified.
    clarification: str = Field(default="", max_length=500)

    @field_validator("clarification")
    @classmethod
    def strip_clarification(cls, value: str) -> str:
        """Normalize model-generated clarification text."""
        return value.strip()


def create_gemini_client():
    """
    Create the Gemini client only when the fallback is actually needed.

    Local intent detection therefore works without a configured API key.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Configure it in backend/.env "
            "to enable complex inventory-question understanding."
        )

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120000),
    )


def extract_analysis_period(question: str, default_days: int = 30) -> int:
    """
    Extract a day-based analysis window from a question.

    Examples:
        "fast moving products in last 14 days" -> 14
        "dead stock for 3 months"              -> 90
        "expiry in next 20 days"                -> 20

    This function only extracts a time window. The inventory service remains
    responsible for applying the correct date semantics for each intent.
    """
    text = question.lower()

    # Match explicit day counts, including forward-looking expiry questions.
    match = re.search(
        r"\b(?:last|past|previous|next|coming|within|for)\s+(\d+)\s+days?\b",
        text,
    )
    if match:
        return min(int(match.group(1)), MAX_ANALYSIS_DAYS)

    # Match week counts.
    match = re.search(
        r"\b(?:last|past|previous|next|coming|within|for)\s+(\d+)\s+weeks?\b",
        text,
    )
    if match:
        return min(int(match.group(1)) * 7, MAX_ANALYSIS_DAYS)

    # Match month counts. A month is treated as 30 days, matching the
    # convention used by the existing Sales Analytics Agent.
    match = re.search(
        r"\b(?:last|past|previous|next|coming|within|for)\s+(\d+)\s+months?\b",
        text,
    )
    if match:
        return min(int(match.group(1)) * 30, MAX_ANALYSIS_DAYS)

    # Common non-numeric periods.
    if any(term in text for term in ("this year", "last year", "past year")):
        return MAX_ANALYSIS_DAYS

    if any(term in text for term in ("this month", "last month", "past month")):
        return 30

    if any(term in text for term in ("this week", "last week", "past week")):
        return 7

    return max(1, min(default_days, MAX_ANALYSIS_DAYS))


def extract_result_limit(question: str) -> int:
    """
    Extract a requested number of products from ranking-style questions.

    The default is ten and the upper bound protects downstream queries from
    unexpectedly large result sets. "Show me 7 ..." is treated as an explicit
    request for seven results, just like "top 7 ...".
    """
    match = re.search(
        r"\b(?:top|first|show me)\s+(\d+)\b",
        question.lower(),
    )

    if not match:
        return 10

    return min(max(int(match.group(1)), 1), MAX_RESULT_LIMIT)


def detect_fast_inventory_intent(
    question: str,
) -> Optional[InventoryIntent]:
    """
    Detect common inventory questions without making an LLM request.

    More specific categories are checked before broad inventory-health
    patterns so a question such as "which items expire soon?" is not
    incorrectly classified as a general inventory summary.
    """
    text = question.lower().strip()
    days = extract_analysis_period(text)
    limit = extract_result_limit(text)

    patterns = {
        "expiry": [
            r"\bexpir(?:y|ies|ing|ation)\b",
            r"\bnear(?:ly)?\s+expir(?:y|ing)\b",
            r"\bexpir(?:y|ing)\s+soon\b",
            r"\b(?:items?|products?|stock)\s+to\s+expire\b",
            r"\bexpired\s+(?:items?|products?|stock)\b",
        ],
        "dead_stock": [
            r"\bdead\s+stock\b",
            r"\bnon[- ]moving\s+(?:stock|products?|items?)\b",
            r"\bunsold\s+(?:stock|products?|items?)\b",
            r"\bproducts?\s+with\s+no\s+sales\b",
            r"\bproducts?\s+(?:have|has)\s+no\s+sales\b",
            r"\b(?:products?|items?|stock)\s+(?:that\s+)?(?:have\s+)?not\s+sold\b",
            r"\bno\s+sales\s+for\s+(?:these\s+)?products?\b",
            r"\b(?:stock|products?)\s+not\s+selling\b",
        ],
        "fast_moving": [
            r"\bfast[- ]moving\b",
            r"\bquick[- ]selling\b",
            r"\bfastest\s+selling\b",
            r"\bmost\s+frequently\s+sold\b",
            r"\bproducts?\s+selling\s+fast\b",
        ],
        "slow_moving": [
            r"\bslow[- ]moving\b",
            r"\bslow\s+selling\b",
            r"\bpoor[- ]selling\b",
            r"\bproducts?\s+(?:are\s+)?selling\s+slow(?:ly)?\b",
        ],
        "stock_coverage": [
            r"\bstock\s+coverage\b",
            r"\bhow\s+many\s+days?\s+(?:will|can)\s+(?:my\s+)?stock\s+last\b",
            r"\bhow\s+long\s+will\s+(?:my\s+)?stock\s+last\b",
            r"\bdays?\s+of\s+stock\b",
            r"\bcover(?:age)?\s+days?\b",
        ],
        "low_stock": [
            r"\blow[- ]stock\b",
            r"\b(?:items?|products?)\s+(?:are\s+)?running\s+low\b",
            r"\bwhich\s+(?:items?|products?)\s+(?:need|needs)\s+restock(?:ing)?\b",
            r"\bwhat\s+(?:do\s+i|should\s+i)\s+restock\b",
            r"\bstock\s+below\s+(?:minimum|threshold|limit)\b",
            r"\breorder\s+alert\b",
        ],
        "data_readiness": [
            r"\bdata\s+readiness\b",
            r"\benough\s+sales\s+data\b",
            r"\bsales\s+data\s+(?:available|enough|sufficient)\b",
            r"\b(?:is|are)\s+(?:my\s+)?sales\s+data\s+(?:enough|sufficient)\b",
            r"\bcan\s+i\s+(?:forecast|predict)\b",
            r"\bforecast(?:ing)?\s+readiness\b",
        ],
        "inventory_health": [
            r"\binventory\s+health\b",
            r"\bstock\s+health\b",
            r"\binventory\s+summary\b",
            r"\boverall\s+inventory\b",
            r"\bhow\s+is\s+my\s+inventory\b",
            r"\bhow\s+is\s+my\s+stock\b",
        ],
    }

    # Keep the order aligned with specificity, not with business priority.
    for intent_name, intent_patterns in patterns.items():
        if any(re.search(pattern, text) for pattern in intent_patterns):
            return InventoryIntent(
                intent=intent_name,
                days=days,
                limit=limit,
            )

    return None


def understand_inventory_question(question: str) -> InventoryIntent:
    """
    Convert a natural-language question into a validated inventory intent.

    Local Python rules handle common questions first. Gemini is used only
    when those rules return no confident match. The Gemini response is
    constrained by the InventoryIntent schema.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter an inventory-related question.")

    question = question.strip()

    if len(question) > MAX_QUESTION_LENGTH:
        raise ValueError(
            f"Question must not exceed {MAX_QUESTION_LENGTH} characters."
        )

    # First choice: fast, deterministic classification.
    fast_result = detect_fast_inventory_intent(question)
    if fast_result is not None:
        return fast_result

    # Second choice: use Gemini for questions that need language understanding.
    client = create_gemini_client()

    system_instruction = """
You are the question-understanding component of KiranaAI.

Classify the user's question into exactly one supported inventory intent.

Supported intents:

low_stock:
Products that are below their minimum stock level, running low, or need
replenishment attention.

stock_coverage:
How many days the current stock is expected to last, based on available
sales-rate information.

dead_stock:
Products with stock on hand but no recorded sales in the selected period.

fast_moving:
Products selling quickly or with the highest sales movement.

slow_moving:
Products with low sales movement over the selected period.

expiry:
Expired products, products nearing expiry, and expiry-related stock.

data_readiness:
Whether enough reliable historical sales and product data exists for
inventory analysis or demand forecasting.

inventory_health:
A broad overview of inventory condition, including stock, movement, and
expiry indicators.

unknown:
Questions unrelated to the supported inventory analyses, or questions that
cannot be confidently classified.

Rules:
- Do not invent stock figures, sales quantities, dates, or recommendations.
- Do not answer the user's question; classify it only.
- Use 30 days as the default analysis period.
- Interpret one month as 30 days and one year as 365 days.
- Default result limit is 10.
- Keep days between 1 and 365 and limit between 1 and 100.
- Sales revenue questions belong to the Sales Analytics Agent.
- Purchase creation, supplier communication, and stock updates are not
  supported actions for this read-only agent.
- If the question is unclear, use unknown and provide a short clarification.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=InventoryIntent,
                temperature=0.1,
            ),
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")

        result = InventoryIntent.model_validate_json(response.text)

        # Apply the same local extraction for predictable defaults and bounds.
        # Explicit values returned by Gemini are retained when valid.
        if result.days == 30:
            result.days = extract_analysis_period(question)

        if result.limit == 10:
            result.limit = extract_result_limit(question)

        return result

    except Exception as error:
        # Keep the underlying exception for logs while exposing a stable,
        # user-friendly error to the API layer.
        raise RuntimeError(
            "Unable to understand the inventory question. "
            "Please rephrase it or try a more specific stock question."
        ) from error



def format_inventory_answer(
    question: str,
    intent: str,
    analytics_data: dict,
) -> str:
    """
    Turn deterministic service results into a concise owner-facing answer.

    This formatter deliberately uses only values returned by the database
    service. It does not ask an LLM to fill gaps or invent recommendations.
    """
    if not isinstance(analytics_data, dict):
        raise ValueError("Inventory analysis returned an invalid result.")

    if intent == "data_readiness":
        summary = analytics_data.get("summary", {})
        readiness = analytics_data.get("readiness", {})
        return (
            f"Data readiness: {readiness.get('status', 'unknown')}. "
            f"{readiness.get('message', '')} "
            f"Active products: {summary.get('total_active_products', 0)}; "
            f"mature products: {summary.get('mature_products', 0)}; "
            f"products with recorded sales: {summary.get('products_with_sales', 0)}; "
            f"units sold in the last 30 days: {summary.get('total_units_sold', 0)}."
        )

    if intent == "inventory_health":
        summary = analytics_data.get("summary", {})
        readiness = analytics_data.get("data_readiness", {})
        return (
            "Inventory health summary: "
            f"{summary.get('out_of_stock_products', 0)} out of stock, "
            f"{summary.get('critical_stock_products', 0)} critical, "
            f"{summary.get('low_stock_products', 0)} low stock, "
            f"{summary.get('healthy_products', 0)} healthy, "
            f"{summary.get('unknown_demand_products', 0)} with unknown demand. "
            f"Expired or expiring batches: "
            f"{summary.get('expired_or_expiring_batches', 0)}. "
            f"Data readiness: {readiness.get('status', 'unknown')}."
        )

    rows = analytics_data.get("products")
    row_label = "products"
    if rows is None:
        rows = analytics_data.get("batches", [])
        row_label = "batches"

    count = analytics_data.get("count", len(rows or []))
    period = analytics_data.get(
        "analysis_period_days",
        analytics_data.get("horizon_days"),
    )

    if not rows:
        period_text = f" in the selected {period}-day period" if period else ""
        return f"No matching inventory {row_label} were found{period_text}."

    lines = [f"Found {count} matching {row_label}."]
    if period:
        lines.append(f"Analysis period: {period} days.")

    for row in rows:
        name = row.get("product_name", "Unnamed product")
        if intent == "low_stock":
            lines.append(
                f"- {name}: {row.get('current_stock')} {row.get('unit') or ''} "
                f"in stock; minimum {row.get('minimum_stock')}; "
                f"shortfall {row.get('shortfall')}."
            )
        elif intent == "stock_coverage":
            remaining = row.get("estimated_days_remaining")
            remaining_text = (
                f"{remaining} days remaining" if remaining is not None
                else "demand rate unknown"
            )
            lines.append(
                f"- {name}: {row.get('saleable_stock')} {row.get('unit') or ''} "
                f"saleable stock; {remaining_text}; status "
                f"{row.get('stock_status')}."
            )
        elif intent == "dead_stock":
            lines.append(
                f"- {name}: {row.get('current_stock')} {row.get('unit') or ''} "
                f"on hand; no recorded sales for {row.get('days_without_recorded_sales')} "
                f"days; estimated stock value {row.get('estimated_stock_value')}."
            )
        elif intent in {"fast_moving", "slow_moving"}:
            lines.append(
                f"- {name}: {row.get('units_sold')} {row.get('unit') or ''} "
                f"sold; average {row.get('average_daily_sales')} per day; "
                f"current recorded stock {row.get('current_stock')}."
            )
        elif intent == "expiry":
            state = "expired" if row.get("is_expired") else "not yet expired"
            lines.append(
                f"- {name}, batch {row.get('batch_number')}: "
                f"{row.get('quantity')} {row.get('unit') or ''}; "
                f"expiry {row.get('expiry_date')} ({state}); "
                f"verified: {row.get('is_verified')}."
            )

    return "\n".join(lines)
