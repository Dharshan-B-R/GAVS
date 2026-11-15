"""Tenant isolation, supplier workspace and goods receipt API tests."""
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement


def register_owner(client, email):
    response = client.post("/auth/register/owner", json={
        "full_name": "Shop Owner",
        "email": email,
        "phone": "9876543210",
        "password": "KiranaTest@123",
        "shop_name": "Test Shop " + email,
        "shop_address": "Bengaluru",
    })
    assert response.status_code == 201
    return response.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_inventory_low_stock_requires_shop_membership(client, db_session):
    first = register_owner(client, "first-owner@example.com")
    second = register_owner(client, "second-owner@example.com")
    shop_id = first["shop"]["id"]

    response = client.get("/products/low-stock", params={"shop_id": shop_id})
    assert response.status_code == 401

    response = client.get(
        "/products/low-stock",
        params={"shop_id": shop_id},
        headers=auth(second["access_token"]),
    )
    assert response.status_code == 403

    db_session.add(Product(
        shop_id=shop_id, name="Rice", quantity=2, minimum_stock=5,
        purchase_price=40, selling_price=50, unit="kg", is_active=True,
    ))
    db_session.flush()
    response = client.get(
        "/products/low-stock",
        params={"shop_id": shop_id},
        headers=auth(first["access_token"]),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Rice"


def test_owner_can_receive_purchase_order_and_stock_is_audited(client, db_session):
    owner = register_owner(client, "receipt-owner@example.com")
    shop_id = owner["shop"]["id"]
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Supplier User",
        "email": "supplier-receipt@example.com",
        "password": "SupplierPass@123",
        "business_name": "Test Wholesale",
    })
    assert supplier_response.status_code == 201
    supplier_id = supplier_response.json()["supplier"]["id"]

    connection = client.post(
        f"/shops/{shop_id}/distributors",
        headers=auth(owner["access_token"]),
        json={"supplier_id": supplier_id},
    )
    assert connection.status_code == 201

    product = Product(
        shop_id=shop_id, name="Cooking Oil", quantity=0, minimum_stock=5,
        purchase_price=100, selling_price=120, unit="litre", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    purchase = Purchase(
        shop_id=shop_id, supplier_id=supplier_id,
        invoice_number="KIRANAAI-PO-TEST", total_amount=200,
        payment_status="pending", status="ordered",
    )
    db_session.add(purchase)
    db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, product_id=product.id,
        quantity=2, unit_price=100, subtotal=200,
    )
    db_session.add(item)
    db_session.flush()

    response = client.post(
        f"/shops/{shop_id}/purchases/{purchase.id}/receive",
        headers=auth(owner["access_token"]),
        json={"items": [{
            "purchase_item_id": item.id,
            "batch_number": "OIL-BATCH-001",
            "expiry_date": "2027-12-31",
        }]},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(product)
    db_session.refresh(purchase)
    db_session.refresh(item)
    assert product.quantity == 2
    assert purchase.status == "received"
    assert item.batch_id is not None
    assert db_session.query(ProductBatch).filter_by(id=item.batch_id).one().is_verified is False
    movement = db_session.query(StockMovement).filter_by(reference_id=purchase.id).one()
    assert movement.quantity_change == 2
    assert movement.quantity_before == 0
    assert movement.quantity_after == 2

    repeated = client.post(
        f"/shops/{shop_id}/purchases/{purchase.id}/receive",
        headers=auth(owner["access_token"]),
        json={"items": [{
            "purchase_item_id": item.id,
            "batch_number": "OIL-BATCH-001",
            "expiry_date": "2027-12-31",
        }]},
    )
    assert repeated.status_code == 200
    db_session.refresh(product)
    assert product.quantity == 2


def test_supplier_can_only_confirm_own_purchase_order(client, db_session):
    owner = register_owner(client, "order-owner@example.com")
    shop_id = owner["shop"]["id"]
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Supplier User",
        "email": "supplier-orders@example.com",
        "password": "SupplierPass@123",
        "business_name": "Supplier Orders Ltd",
    })
    supplier_id = supplier_response.json()["supplier"]["id"]
    product = Product(
        shop_id=shop_id, name="Soap", quantity=0, minimum_stock=2,
        purchase_price=20, selling_price=25, unit="pieces", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    purchase = Purchase(
        shop_id=shop_id, supplier_id=supplier_id,
        invoice_number="KIRANAAI-PO-SUP", total_amount=100,
        payment_status="pending", status="ordered",
    )
    db_session.add(purchase)
    db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, product_id=product.id,
        quantity=5, unit_price=20, subtotal=100,
    ))
    db_session.flush()

    supplier_token = supplier_response.json()["access_token"]
    orders = client.get("/supplier/orders", headers=auth(supplier_token))
    assert orders.status_code == 200
    assert len(orders.json()) == 1
    assert orders.json()[0]["purchase_id"] == purchase.id

    confirmed = client.post(
        f"/supplier/orders/{purchase.id}/confirm",
        headers=auth(supplier_token),
    )
    assert confirmed.status_code == 200
    db_session.refresh(purchase)
    assert purchase.status == "confirmed"



def test_owner_approval_purchase_order_supplier_confirmation_and_receipt(client, db_session):
    owner = register_owner(client, "full-flow-owner@example.com")
    shop_id = owner["shop"]["id"]
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Full Flow Supplier",
        "email": "full-flow-supplier@example.com",
        "password": "SupplierPass@123",
        "business_name": "Full Flow Wholesale",
    })
    supplier_id = supplier_response.json()["supplier"]["id"]
    assert client.post(
        f"/shops/{shop_id}/distributors",
        headers=auth(owner["access_token"]),
        json={"supplier_id": supplier_id},
    ).status_code == 201

    product = Product(
        shop_id=shop_id, name="Wheat Flour", quantity=0, minimum_stock=4,
        purchase_price=30, selling_price=40, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    budget = client.put(
        f"/shops/{shop_id}/purchase-budget",
        headers=auth(owner["access_token"]),
        json={"available_amount": "1000.00", "currency": "INR"},
    )
    assert budget.status_code == 200

    proposal = client.post(
        f"/shops/{shop_id}/purchase-proposals",
        headers=auth(owner["access_token"]),
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product.id, "quantity": "5", "unit_price": "30"}],
            "rationale": "Test reorder",
        },
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["proposal_id"]

    approval = client.post(
        f"/shops/{shop_id}/purchase-proposals/{proposal_id}/decision",
        headers=auth(owner["access_token"]),
        json={"approve": True, "note": "Approved by owner"},
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved"

    execution = client.post(
        f"/shops/{shop_id}/purchase-proposals/{proposal_id}/execute",
        headers=auth(owner["access_token"]),
    )
    assert execution.status_code == 200, execution.text
    purchase_id = execution.json()["purchase_id"]
    assert execution.json()["purchase_status"] == "ordered"
    db_session.refresh(product)
    assert product.quantity == 0
    purchase = db_session.query(Purchase).filter_by(id=purchase_id).one()
    purchase_item = db_session.query(PurchaseItem).filter_by(purchase_id=purchase_id).one()
    assert purchase.status == "ordered"
    assert purchase_item.batch_id is None

    supplier_token = supplier_response.json()["access_token"]
    supplier_orders = client.get("/supplier/orders", headers=auth(supplier_token))
    assert supplier_orders.status_code == 200
    assert supplier_orders.json()[0]["purchase_id"] == purchase_id

    confirmation = client.post(
        f"/supplier/orders/{purchase_id}/confirm",
        headers=auth(supplier_token),
    )
    assert confirmation.status_code == 200

    receipt = client.post(
        f"/shops/{shop_id}/purchases/{purchase_id}/receive",
        headers=auth(owner["access_token"]),
        json={"items": [{
            "purchase_item_id": purchase_item.id,
            "batch_number": "WHEAT-2026-01",
            "expiry_date": "2027-06-30",
        }]},
    )
    assert receipt.status_code == 200, receipt.text
    db_session.refresh(product)
    db_session.refresh(purchase)
    assert product.quantity == 5
    assert purchase.status == "received"



def test_shop_staff_can_record_sale_and_stock_is_deducted_from_verified_batch(client, db_session):
    owner = register_owner(client, "sales-owner@example.com")
    shop_id = owner["shop"]["id"]
    product = Product(
        shop_id=shop_id, name="Sugar", quantity=10, minimum_stock=2,
        purchase_price=35, selling_price=45, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    batch = ProductBatch(
        product_id=product.id, batch_number="SUGAR-001",
        expiry_date=__import__("datetime").date(2027, 12, 31),
        quantity=10, purchase_price=35, is_verified=True,
    )
    db_session.add(batch)
    db_session.flush()

    response = client.post(
        "/sales",
        params={"shop_id": shop_id},
        headers=auth(owner["access_token"]),
        json={
            "items": [{"product_id": product.id, "quantity": 2, "discount_amount": 0}],
            "discount_amount": 0,
            "payment_method": "cash",
        },
    )
    assert response.status_code == 200, response.text
    db_session.refresh(product)
    db_session.refresh(batch)
    assert product.quantity == 8
    assert batch.quantity == 8
    assert response.json()["total_amount"] == 90
