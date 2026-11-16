"""Consolidated Phase 2 API journey against the isolated kiranaai_test database.

This is an integration smoke test, not a replacement for focused service tests.
It creates its own owner/shop and exercises the main authenticated workflows.
"""
from datetime import date, timedelta


def test_phase2_end_to_end_owner_journey(client):
    # 1. Register and authenticate a fresh shop owner.
    registration = client.post(
        "/auth/register/owner",
        json={
            "full_name": "Phase Two Test Owner",
            "email": "phase2-journey@example.com",
            "phone": "9876501234",
            "password": "PhaseTwoTest@123",
            "shop_name": "Phase Two Journey Store",
            "shop_address": "Bengaluru",
            "shop_phone": "9876501234",
        },
    )
    assert registration.status_code == 201, registration.text
    registration_data = registration.json()
    shop_id = registration_data["shop"]["id"]
    headers = {"Authorization": f"Bearer {registration_data['access_token']}"}

    shops = client.get("/auth/shops", headers=headers)
    assert shops.status_code == 200, shops.text
    assert any(shop["shop_id"] == shop_id for shop in shops.json())

    # 2. Create a catalog item and verify inventory views.
    product = client.post(
        f"/products?shop_id={shop_id}",
        headers=headers,
        json={
            "name": "Phase Two Test Rice",
            "category": "Grocery",
            "barcode": "PHASE2-RICE-001",
            "quantity": 0,
            "minimum_stock": 5,
            "purchase_price": 40,
            "selling_price": 50,
            "unit": "kg",
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    products = client.get(f"/products?shop_id={shop_id}", headers=headers)
    assert products.status_code == 200, products.text
    assert any(item["id"] == product_id for item in products.json())

    inventory = client.get(f"/inventory/summary?shop_id={shop_id}", headers=headers)
    assert inventory.status_code == 200, inventory.text
    assert inventory.json()["total_products"] >= 1

    # 3. Exercise the intelligence specialists. Empty-history responses are
    # valid for a brand-new shop; each route must still respond successfully.
    intelligence_routes = [
        f"/shops/{shop_id}/agents/forecast",
        f"/shops/{shop_id}/agents/seasonal-demand",
        f"/shops/{shop_id}/agents/stockout-risk",
        f"/shops/{shop_id}/agents/dead-stock",
        f"/shops/{shop_id}/agents/expiry-risk",
        f"/shops/{shop_id}/agents/reorder-recommendations",
        f"/shops/{shop_id}/agents/supplier-prices",
        f"/shops/{shop_id}/agents/supplier-performance",
        f"/shops/{shop_id}/agents/financial-position",
        f"/shops/{shop_id}/agents/suppliers",
    ]
    for route in intelligence_routes:
        response = client.get(route, headers=headers)
        assert response.status_code == 200, f"{route}: {response.status_code} {response.text}"

    # 4. Save a festival/local-demand event and verify it is visible.
    event_date = (date.today() + timedelta(days=45)).isoformat()
    event = client.post(
        f"/shops/{shop_id}/festival-calendar",
        headers=headers,
        json={
            "name": "Phase Two Test Festival",
            "event_date": event_date,
            "event_type": "festival",
            "notes": "Integration test event",
        },
    )
    assert event.status_code == 201, event.text
    event_id = event.json()["event_id"]

    calendar = client.get(f"/shops/{shop_id}/festival-calendar", headers=headers)
    assert calendar.status_code == 200, calendar.text
    assert any(row["event_id"] == event_id for row in calendar.json())

    event_demand = client.get(
        f"/shops/{shop_id}/agents/event-demand",
        params={"event_name": "Phase Two Test Festival", "event_start": event_date},
        headers=headers,
    )
    assert event_demand.status_code == 200, event_demand.text

    # 5. Capture stock availability and verify daily intelligence outputs.
    snapshot = client.post(
        f"/shops/{shop_id}/availability-snapshots/capture",
        headers=headers,
    )
    assert snapshot.status_code == 200, snapshot.text

    snapshots = client.get(
        f"/shops/{shop_id}/availability-snapshots", headers=headers
    )
    assert snapshots.status_code == 200, snapshots.text

    alerts = client.get(f"/shops/{shop_id}/intelligence-alerts?status=all", headers=headers)
    assert alerts.status_code == 200, alerts.text

    generated_summary = client.post(
        f"/shops/{shop_id}/intelligence-daily-summaries/generate",
        headers=headers,
    )
    assert generated_summary.status_code == 200, generated_summary.text

    summaries = client.get(
        f"/shops/{shop_id}/intelligence-daily-summaries", headers=headers
    )
    assert summaries.status_code == 200, summaries.text

    # 6. Exercise customer credit (khata) and owner purchasing controls.
    customer = client.post(
        f"/shops/{shop_id}/customers",
        headers=headers,
        json={"name": "Phase Two Test Customer", "phone": "9876501111"},
    )
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["customer_id"]

    credit = client.post(
        f"/shops/{shop_id}/customers/{customer_id}/khata",
        headers=headers,
        json={
            "transaction_type": "credit",
            "amount": 125,
            "description": "Integration test credit",
        },
    )
    assert credit.status_code == 201, credit.text
    assert credit.json()["outstanding_amount"] == 125

    ledger = client.get(
        f"/shops/{shop_id}/customers/{customer_id}/khata", headers=headers
    )
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["outstanding_amount"] == 125

    budget = client.put(
        f"/shops/{shop_id}/purchase-budget",
        headers=headers,
        json={"available_amount": "5000.00", "currency": "INR"},
    )
    assert budget.status_code == 200, budget.text

    budget_view = client.get(
        f"/shops/{shop_id}/purchase-budget", headers=headers
    )
    assert budget_view.status_code == 200, budget_view.text
    assert budget_view.json()["available_amount"] == "5000.00"

    proposals = client.get(
        f"/shops/{shop_id}/purchase-proposals", headers=headers
    )
    assert proposals.status_code == 200, proposals.text
