"""
Tests for deterministic, database-grounded Inventory Agent answer formatting.
"""

from app.agents.inventory_agent import format_inventory_answer


def test_low_stock_answer_uses_service_values():
    answer = format_inventory_answer(
        question="Show low stock",
        intent="low_stock",
        analytics_data={
            "count": 1,
            "products": [{
                "product_name": "Rice",
                "current_stock": 3,
                "minimum_stock": 10,
                "unit": "kg",
                "shortfall": 7,
            }],
        },
    )

    assert "Found 1 matching products." in answer
    assert "Rice: 3 kg" in answer
    assert "shortfall 7" in answer


def test_stock_coverage_answer_distinguishes_saleable_stock():
    answer = format_inventory_answer(
        question="How many days will stock last?",
        intent="stock_coverage",
        analytics_data={
            "analysis_period_days": 30,
            "count": 1,
            "products": [{
                "product_name": "Cooking Oil",
                "saleable_stock": 12,
                "unit": "L",
                "estimated_days_remaining": 4.0,
                "stock_status": "low_stock",
            }],
        },
    )

    assert "12 L saleable stock" in answer
    assert "4.0 days remaining" in answer


def test_empty_result_is_reported_without_inventing_products():
    answer = format_inventory_answer(
        question="Show dead stock",
        intent="dead_stock",
        analytics_data={"count": 0, "products": []},
    )

    assert answer == "No matching inventory products were found."


def test_data_readiness_answer_uses_readiness_summary():
    answer = format_inventory_answer(
        question="Is my sales data enough?",
        intent="data_readiness",
        analytics_data={
            "summary": {
                "total_active_products": 20,
                "mature_products": 15,
                "products_with_sales": 8,
                "total_units_sold": 120,
            },
            "readiness": {
                "status": "ready_for_initial_detection",
                "message": "Validate sales coverage before decisions.",
            },
        },
    )

    assert "ready_for_initial_detection" in answer
    assert "Active products: 20" in answer
    assert "units sold in the last 30 days: 120" in answer


def test_inventory_health_answer_summarizes_status_counts():
    answer = format_inventory_answer(
        question="Check inventory health",
        intent="inventory_health",
        analytics_data={
            "summary": {
                "out_of_stock_products": 2,
                "critical_stock_products": 3,
                "low_stock_products": 4,
                "healthy_products": 10,
                "unknown_demand_products": 1,
                "expired_or_expiring_batches": 5,
            },
            "data_readiness": {"status": "ready_for_initial_detection"},
        },
    )

    assert "2 out of stock" in answer
    assert "5" in answer
    assert "ready_for_initial_detection" in answer
