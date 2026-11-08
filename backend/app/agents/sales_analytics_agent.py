
# ---------------------------------------------------------
# KIRANAAI SALES ANALYTICS AGENT
# Purpose:
# Understand sales questions using hybrid intent detection.
#
# Responsibilities:
# 1. Detect common questions using fast Python rules.
# 2. Use Gemini for complex or unclear questions.
# 3. Extract the requested analysis period.
# 4. Format answers using verified backend analytics data.
# 5. Avoid unnecessary Gemini API calls.
# ---------------------------------------------------------

import os
import re

from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


# Load environment variables from backend/.env
load_dotenv()


# Gemini model configuration
GEMINI_MODEL = "gemini-3.8-flash"


# ---------------------------------------------------------
# SCHEMA: Sales Intent
# Purpose:
# Stores the intent and parameters extracted from a question.
# ---------------------------------------------------------

class SalesIntent(BaseModel):

    intent: Literal[
        "summary",
        "daily",
        "products",
        "unknown"
    ]

    days: int = Field(default=7, ge=1, le=365)

    limit: int = Field(default=10, ge=1, le=100)

    clarification: str = Field(default="")


# ---------------------------------------------------------
# FUNCTION: Create Gemini Client
# Purpose:
# Create a configured Gemini client for complex questions.
# ---------------------------------------------------------

def create_gemini_client():

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check backend/.env."
        )

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=120000
        )
    )


# ---------------------------------------------------------
# FUNCTION: Extract Analysis Period
# Purpose:
# Identify the requested number of days from the question.
# Defaults to 7 days when no period is specified.
# ---------------------------------------------------------

def extract_analysis_period(question: str) -> int:

    text = question.lower()

    # Match explicit day counts
    match = re.search(
        r"(?:last|past|previous|for)\s+(\d+)\s+days?",
        text
    )

    if match:
        return min(int(match.group(1)), 365)

    # Match week counts
    match = re.search(
        r"(?:last|past|previous|for)\s+(\d+)\s+weeks?",
        text
    )

    if match:
        return min(int(match.group(1)) * 7, 365)

    # Match month counts
    match = re.search(
        r"(?:last|past|previous|for)\s+(\d+)\s+months?",
        text
    )

    if match:
        return min(int(match.group(1)) * 30, 365)

    # Match common period descriptions
    if "this year" in text or "last year" in text:
        return 365

    if "this month" in text or "last month" in text:
        return 30

    if "this week" in text or "last week" in text:
        return 7

    return 7


# ---------------------------------------------------------
# FUNCTION: Detect Fast Sales Intent
# Purpose:
# Identify common sales questions using Python rules.
# Avoids Gemini API calls for recognized questions.
# ---------------------------------------------------------

def detect_fast_sales_intent(question: str):

    text = question.lower().strip()

    days = extract_analysis_period(text)

    # Extract requested product limit
    limit_match = re.search(
        r"(?:top|first)\s+(\d+)",
        text
    )

    limit = (
        min(int(limit_match.group(1)), 100)
        if limit_match
        else 10
    )

    # Product performance questions
    product_patterns = [
        r"\btop[- ]selling\b",
        r"\bbest[- ]selling\b",
        r"\btop products?\b",
        r"\bbest products?\b",
        r"\bwhich products?\b",
        r"\bproducts? sold\b",
        r"\bproduct sales\b",
        r"\bmost popular products?\b"
    ]

    if any(re.search(pattern, text) for pattern in product_patterns):

        return SalesIntent(
            intent="products",
            days=days,
            limit=limit
        )

    # Daily sales questions
    daily_patterns = [
        r"\bdaily sales\b",
        r"\bsales per day\b",
        r"\beach day\b",
        r"\bday[- ]by[- ]day\b",
        r"\bsales trend\b",
        r"\bhighest sales day\b",
        r"\bdaily revenue\b"
    ]

    if any(re.search(pattern, text) for pattern in daily_patterns):

        return SalesIntent(
            intent="daily",
            days=days,
            limit=limit
        )

    # Overall sales summary questions
    summary_patterns = [
        r"\btotal sales\b",
        r"\bsales summary\b",
        r"\bhow much did i sell\b",
        r"\bhow much have i sold\b",
        r"\btotal revenue\b",
        r"\bsales revenue\b",
        r"\baverage bill\b",
        r"\baverage sales\b",
        r"\bnumber of bills\b",
        r"\bitems sold\b",
        r"\btotal bills\b"
    ]

    if any(re.search(pattern, text) for pattern in summary_patterns):

        return SalesIntent(
            intent="summary",
            days=days,
            limit=limit
        )

    # No confident local match: use Gemini fallback
    return None


# ---------------------------------------------------------
# FUNCTION: Understand Sales Question
# Purpose:
# Use Python for common questions and Gemini for complex ones.
# ---------------------------------------------------------

def understand_sales_question(question: str) -> SalesIntent:

    if not question or not question.strip():
        raise ValueError(
            "Please enter a sales-related question."
        )

    question = question.strip()

    if len(question) > 1000:
        raise ValueError(
            "Question must not exceed 1000 characters."
        )

    # FIRST: Try fast local intent detection
    fast_result = detect_fast_sales_intent(question)

    if fast_result is not None:

        print(
            "Sales intent detected locally:",
            fast_result.intent
        )

        return fast_result

    # SECOND: Use Gemini for complex questions
    print("Using Gemini fallback for sales question.")

    client = create_gemini_client()

    system_instruction = """
    You are the question-understanding component of KiranaAI.

    Supported intents:

    summary:
    Overall revenue, bills, items sold and average bill value.

    daily:
    Daily sales trends and highest sales day.

    products:
    Best-selling products, quantities and product revenue.

    unknown:
    Questions outside supported sales analytics.

    Rules:
    - Never invent sales figures.
    - Never calculate revenue.
    - Default period is 7 days.
    - Month means 30 days.
    - Year means 365 days.
    - Default product limit is 10.
    - Inventory and purchasing questions are not sales questions.
    """

    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=SalesIntent,
                temperature=0.1
            )
        )

        if not response.text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        return SalesIntent.model_validate_json(
            response.text
        )

    except Exception as error:

        print(
            "Gemini sales intent error:",
            str(error)
        )

        raise RuntimeError(
            "Unable to understand the sales question."
        ) from error


# ---------------------------------------------------------
# FUNCTION: Format Sales Analytics Answer
# Purpose:
# Generate fast answers using verified backend analytics data.
# Does not make another Gemini API request.
# ---------------------------------------------------------

def format_sales_answer(
    question: str,
    intent: str,
    analytics_data: dict
) -> str:

    # Overall sales summary
    if intent == "summary":

        summary = analytics_data.get("summary", {})

        revenue = float(summary.get("total_revenue", 0))
        bills = int(summary.get("total_bills", 0))
        items = float(summary.get("total_items_sold", 0))
        average = float(summary.get("average_bill_value", 0))

        if bills == 0:
            return (
                "There are no recorded sales "
                "in the selected period."
            )

        return (
            f"Your total sales were ₹{revenue:,.2f}.\n"
            f"Total bills: {bills}\n"
            f"Items sold: {items:g}\n"
            f"Average bill value: ₹{average:,.2f}"
        )

    # Daily sales information
    if intent == "daily":

        daily_sales = analytics_data.get("daily_sales", [])

        if not daily_sales:
            return (
                "There are no recorded sales "
                "in the selected period."
            )

        lines = ["Here is your daily sales summary:"]

        for day in daily_sales:

            lines.append(
                f"{day['date']}: "
                f"₹{float(day['revenue']):,.2f}, "
                f"{day['total_bills']} bill(s), "
                f"{float(day['items_sold']):g} items sold"
            )

        highest = analytics_data.get("highest_sales_day")

        if highest:

            lines.append(
                f"Highest sales day: {highest['date']} "
                f"with ₹{float(highest['revenue']):,.2f}."
            )

        return "\n".join(lines)

    # Product-wise sales information
    if intent == "products":

        products = analytics_data.get("products", [])

        if not products:
            return (
                "There are no recorded product sales "
                "in the selected period."
            )

        lines = ["Here are your best-selling products:"]

        for product in products:

            lines.append(
                f"{product['rank']}. "
                f"{product['product_name']} - "
                f"{float(product['total_quantity_sold']):g} "
                f"{product['unit']} sold, "
                f"item revenue ₹"
                f"{float(product['total_revenue']):,.2f}"
            )

        return "\n".join(lines)

    return (
        "I could not prepare an answer "
        "for this sales question."
    )
