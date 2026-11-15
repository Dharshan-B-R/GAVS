"""
Tests for the KiranaAI Inventory Agent.

These tests focus on deterministic Python intent detection and validation.
They deliberately avoid Gemini and the database so they run quickly and
remain reliable in local development and CI environments.
"""

import pytest
from pydantic import ValidationError

from app.agents.inventory_agent import (
    InventoryIntent,
    detect_fast_inventory_intent,
    extract_analysis_period,
    extract_result_limit,
    understand_inventory_question,
)


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("Show me low-stock products", "low_stock"),
        ("Which items are running low?", "low_stock"),
        ("How many days will my stock last?", "stock_coverage"),
        ("Show stock coverage for last 14 days", "stock_coverage"),
        ("Find dead stock", "dead_stock"),
        ("Which products have no sales?", "dead_stock"),
        ("Show me products that have not sold in the last 90 days", "dead_stock"),
        ("Show items not sold in the last 30 days", "dead_stock"),
        ("Show fast-moving products", "fast_moving"),
        ("What are my best quick-selling items?", "fast_moving"),
        ("Show slow-moving products", "slow_moving"),
        ("Which products are selling slowly?", "slow_moving"),
        ("Which products are expiring soon?", "expiry"),
        ("Show expired stock", "expiry"),
        ("Is my sales data enough for forecasting?", "data_readiness"),
        ("Check inventory health", "inventory_health"),
        ("Give me an inventory summary", "inventory_health"),
    ],
)
def test_fast_inventory_intent_detection(question, expected_intent):
    """Recognize common inventory questions without calling Gemini."""
    result = detect_fast_inventory_intent(question)

    assert result is not None
    assert result.intent == expected_intent


def test_unrecognized_question_returns_none_from_fast_detector():
    """Leave unrelated questions for the fallback classifier."""
    assert detect_fast_inventory_intent("What is the weather today?") is None


@pytest.mark.parametrize(
    ("question", "expected_days"),
    [
        ("Show stock for last 14 days", 14),
        ("Dead stock in past 2 weeks", 14),
        ("Expiry in next 3 months", 90),
        ("Show inventory this month", 30),
        ("Show inventory last week", 7),
        ("Show inventory this year", 365),
        ("Show inventory", 30),
    ],
)
def test_extract_analysis_period(question, expected_days):
    """Extract supported time periods and apply the 30-day default."""
    assert extract_analysis_period(question) == expected_days


def test_analysis_period_is_capped_at_365_days():
    """Prevent a requested period from exceeding the supported maximum."""
    assert extract_analysis_period("Show sales for last 900 days") == 365


@pytest.mark.parametrize(
    ("question", "expected_limit"),
    [
        ("Show top 5 fast-moving products", 5),
        ("Show first 3 low-stock products", 3),
        ("Show me 7 dead stock items", 7),
        ("Show top 500 slow-moving products", 100),
        ("Show top 0 products", 1),
    ],
)
def test_extract_result_limit(question, expected_limit):
    """Apply the default and safe bounds to ranked result limits."""
    assert extract_result_limit(question) == expected_limit


def test_understand_inventory_question_uses_local_detection():
    """A recognized question should not require a Gemini API key."""
    result = understand_inventory_question("Show low-stock products")

    assert isinstance(result, InventoryIntent)
    assert result.intent == "low_stock"
    assert result.days == 30
    assert result.limit == 10


@pytest.mark.parametrize("question", ["", "   ", None])
def test_understand_inventory_question_rejects_empty_input(question):
    """Reject missing questions before attempting any model call."""
    with pytest.raises(ValueError, match="inventory-related question"):
        understand_inventory_question(question)


def test_understand_inventory_question_rejects_oversized_input():
    """Protect the classifier from excessively long user input."""
    question = "inventory " * 120

    with pytest.raises(ValueError, match="must not exceed 1000 characters"):
        understand_inventory_question(question)


def test_inventory_intent_rejects_invalid_intent():
    """Only explicitly supported intent labels should be accepted."""
    with pytest.raises(ValidationError):
        InventoryIntent(intent="place_purchase_order")


def test_inventory_intent_enforces_days_and_limit_bounds():
    """Validate period and result limits even for model-generated output."""
    with pytest.raises(ValidationError):
        InventoryIntent(intent="low_stock", days=500)

    with pytest.raises(ValidationError):
        InventoryIntent(intent="low_stock", limit=500)


def test_inventory_intent_strips_clarification_text():
    """Normalize optional clarification text from the fallback model."""
    result = InventoryIntent(
        intent="unknown",
        clarification="  Please clarify your inventory question.  ",
    )

    assert result.clarification == "Please clarify your inventory question."
