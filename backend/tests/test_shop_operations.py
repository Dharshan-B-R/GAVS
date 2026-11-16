"""Tenant isolation, supplier workspace and goods receipt API tests."""
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product_batch import ProductBatch
from app.models.stock_movement import StockMovement
from app.models.shop_membership import ShopMembership


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



def test_legacy_unscoped_data_endpoints_are_disabled(client):
    assert client.get("/inventory/expiry-intelligence").status_code == 410
    assert client.get("/analytics/sales/summary").status_code == 410
    assert client.get("/suppliers").status_code == 410
    assert client.get("/stock-movements").status_code == 410


def test_supplier_cannot_access_shop_owner_purchase_budget(client):
    owner = register_owner(client, "supplier-denied-owner@example.com")
    supplier = client.post("/auth/register/distributor", json={
        "full_name": "Supplier Account",
        "email": "supplier-denied@example.com",
        "password": "SupplierPass@123",
        "business_name": "Supplier Denied Ltd",
    })
    response = client.get(
        f"/shops/{owner['shop']['id']}/purchase-budget",
        headers=auth(supplier.json()["access_token"]),
    )
    assert response.status_code == 403



def test_owner_can_suspend_and_reactivate_employee_membership(client):
    owner = register_owner(client, "employee-admin-owner@example.com")
    shop_id = owner["shop"]["id"]
    invitation = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": "managed-employee@example.com"},
    )
    accepted = client.post(
        "/auth/employees/accept-invitation",
        json={
            "invitation_token": invitation.json()["invitation_token"],
            "full_name": "Managed Employee",
            "password": "EmployeePass@123",
        },
    )
    employee_id = accepted.json()["user"]["id"]
    suspended = client.patch(
        f"/shops/{shop_id}/employees/{employee_id}/status",
        headers=auth(owner["access_token"]),
        json={"is_active": False},
    )
    assert suspended.status_code == 200
    employee_login = client.post(
        "/auth/login",
        data={"username": "managed-employee@example.com", "password": "EmployeePass@123"},
    )
    employee_shops = client.get(
        "/auth/shops",
        headers=auth(employee_login.json()["access_token"]),
    )
    assert employee_shops.status_code == 200
    assert employee_shops.json() == []

    reactivated = client.patch(
        f"/shops/{shop_id}/employees/{employee_id}/status",
        headers=auth(owner["access_token"]),
        json={"is_active": True},
    )
    assert reactivated.status_code == 200
    employee_shops = client.get(
        "/auth/shops",
        headers=auth(employee_login.json()["access_token"]),
    )
    assert len(employee_shops.json()) == 1



def test_stock_adjustment_creates_batch_and_requires_verification(client, db_session):
    owner = register_owner(client, "adjustment-owner@example.com")
    shop_id = owner["shop"]["id"]
    product = Product(
        shop_id=shop_id, name="Tea", quantity=0, minimum_stock=1,
        purchase_price=200, selling_price=240, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    missing_batch = client.post(
        f"/shops/{shop_id}/inventory/adjustments",
        headers=auth(owner["access_token"]),
        json={"product_id": product.id, "quantity_change": 3, "reason": "Opening stock"},
    )
    assert missing_batch.status_code == 422

    added = client.post(
        f"/shops/{shop_id}/inventory/adjustments",
        headers=auth(owner["access_token"]),
        json={
            "product_id": product.id,
            "quantity_change": 3,
            "reason": "Opening stock",
            "batch_number": "TEA-OPEN-001",
            "expiry_date": "2027-12-31",
        },
    )
    assert added.status_code == 201, added.text
    db_session.refresh(product)
    batch = db_session.query(ProductBatch).filter_by(product_id=product.id).one()
    assert product.quantity == 3
    assert batch.quantity == 3
    assert batch.is_verified is False

    verified = client.post(
        f"/product-batches/{batch.id}/verify",
        params={"shop_id": shop_id},
        headers=auth(owner["access_token"]),
        json={"verified_quantity": 3, "reason": "Physical count"},
    )
    assert verified.status_code == 200, verified.text
    db_session.refresh(batch)
    assert batch.is_verified is True

    reduced = client.post(
        f"/shops/{shop_id}/inventory/adjustments",
        headers=auth(owner["access_token"]),
        json={"product_id": product.id, "quantity_change": -1, "reason": "Wastage"},
    )
    assert reduced.status_code == 201
    db_session.refresh(product)
    db_session.refresh(batch)
    assert product.quantity == 2
    assert batch.quantity == 2



def test_employee_can_read_inventory_but_cannot_access_owner_budget(client):
    owner = register_owner(client, "employee-scope-owner@example.com")
    shop_id = owner["shop"]["id"]
    invite = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": "employee-scope@example.com"},
    )
    accepted = client.post(
        "/auth/employees/accept-invitation",
        json={
            "invitation_token": invite.json()["invitation_token"],
            "full_name": "Inventory Employee",
            "password": "EmployeePass@123",
        },
    )
    employee_token = accepted.json()["access_token"]

    inventory = client.get(
        "/products/low-stock",
        params={"shop_id": shop_id},
        headers=auth(employee_token),
    )
    assert inventory.status_code == 200

    budget = client.get(
        f"/shops/{shop_id}/purchase-budget",
        headers=auth(employee_token),
    )
    assert budget.status_code == 403



def test_employee_ai_cannot_read_owner_budget_or_pending_approvals(client):
    owner = register_owner(client, "employee-ai-owner@example.com")
    shop_id = owner["shop"]["id"]
    invite = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": "employee-ai@example.com"},
    )
    accepted = client.post(
        "/auth/employees/accept-invitation",
        json={
            "invitation_token": invite.json()["invitation_token"],
            "full_name": "AI Employee",
            "password": "EmployeePass@123",
        },
    )
    response = client.post(
        f"/shops/{shop_id}/agents/orchestrate",
        headers=auth(accepted.json()["access_token"]),
        json={"question": "What is my cash available and pending order?"},
    )
    assert response.status_code == 200, response.text
    assert "budget" in response.json()["restricted_agents"]
    assert "approval" in response.json()["restricted_agents"]
    assert "budget" not in response.json()["results"]
    assert "approval" not in response.json()["results"]



def test_purchase_approval_cannot_exceed_cash_budget(client, db_session):
    owner = register_owner(client, "budget-guard-owner@example.com")
    shop_id = owner["shop"]["id"]
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Budget Supplier",
        "email": "budget-supplier@example.com",
        "password": "SupplierPass@123",
        "business_name": "Budget Wholesale",
    })
    supplier_id = supplier_response.json()["supplier"]["id"]
    client.post(
        f"/shops/{shop_id}/distributors",
        headers=auth(owner["access_token"]),
        json={"supplier_id": supplier_id},
    )
    product = Product(
        shop_id=shop_id, name="Detergent", quantity=0, minimum_stock=1,
        purchase_price=100, selling_price=120, unit="pack", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    client.put(
        f"/shops/{shop_id}/purchase-budget",
        headers=auth(owner["access_token"]),
        json={"available_amount": "100.00", "currency": "INR"},
    )
    proposal = client.post(
        f"/shops/{shop_id}/purchase-proposals",
        headers=auth(owner["access_token"]),
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product.id, "quantity": "2", "unit_price": "100"}],
        },
    )
    assert proposal.status_code == 201
    proposal_id = proposal.json()["proposal_id"]
    approval = client.post(
        f"/shops/{shop_id}/purchase-proposals/{proposal_id}/decision",
        headers=auth(owner["access_token"]),
        json={"approve": True},
    )
    assert approval.status_code == 409
    assert db_session.query(Purchase).filter(Purchase.shop_id == shop_id).count() == 0



def test_legacy_positive_stock_can_be_assigned_to_opening_batch_once(client, db_session):
    owner = register_owner(client, "legacy-stock-owner@example.com")
    shop_id = owner["shop"]["id"]
    product = Product(
        shop_id=shop_id, name="Legacy Rice", quantity=7, minimum_stock=2,
        purchase_price=40, selling_price=50, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/shops/{shop_id}/products/{product.id}/opening-batch",
        headers=auth(owner["access_token"]),
        json={"batch_number": "LEGACY-RICE-01", "expiry_date": "2027-12-31"},
    )
    assert response.status_code == 201, response.text
    db_session.refresh(product)
    batch = db_session.query(ProductBatch).filter_by(product_id=product.id).one()
    assert product.quantity == 7
    assert batch.quantity == 7
    assert batch.is_verified is False

    duplicate = client.post(
        f"/shops/{shop_id}/products/{product.id}/opening-batch",
        headers=auth(owner["access_token"]),
        json={"batch_number": "LEGACY-RICE-02", "expiry_date": "2027-12-31"},
    )
    assert duplicate.status_code == 409


def test_owner_can_revoke_pending_employee_invitation(client):
    owner = register_owner(client, "employee-invite-owner@example.com")
    shop_id = owner["shop"]["id"]
    invited = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": "new-employee@example.com"},
    )
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["invitation_id"]
    listed = client.get(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
    )
    assert listed.status_code == 200
    assert any(row["invitation_id"] == invitation_id and row["status"] == "pending"
               for row in listed.json())

    revoked = client.delete(
        f"/auth/shops/{shop_id}/employees/invitations/{invitation_id}",
        headers=auth(owner["access_token"]),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    accepted = client.post("/auth/employees/accept-invitation", json={
        "invitation_token": invited.json()["invitation_token"],
        "full_name": "New Employee",
        "password": "EmployeePass@123",
    })
    assert accepted.status_code == 404


def test_supplier_can_update_only_its_own_profile(client):
    first = client.post("/auth/register/distributor", json={
        "full_name": "First Supplier",
        "email": "first-profile-supplier@example.com",
        "password": "SupplierPass@123",
        "business_name": "First Wholesale",
    })
    second = client.post("/auth/register/distributor", json={
        "full_name": "Second Supplier",
        "email": "second-profile-supplier@example.com",
        "password": "SupplierPass@123",
        "business_name": "Second Wholesale",
    })
    assert first.status_code == 201 and second.status_code == 201

    updated = client.put("/supplier/profile", headers=auth(first.json()["access_token"]), json={
        "name": "First Wholesale Updated",
        "contact_person": "Updated Contact",
        "phone": "9876543210",
        "address": "Bengaluru",
        "gstin": None,
        "notes": "Delivers grocery items",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "First Wholesale Updated"

    own_profile = client.get("/supplier/profile", headers=auth(first.json()["access_token"]))
    other_profile = client.get("/supplier/profile", headers=auth(second.json()["access_token"]))
    assert own_profile.status_code == 200
    assert own_profile.json()["name"] == "First Wholesale Updated"
    assert other_profile.status_code == 200
    assert other_profile.json()["name"] == "Second Wholesale"


def test_employee_has_shop_access_but_not_owner_financial_controls(client):
    owner = register_owner(client, "employee-permission-owner@example.com")
    shop_id = owner["shop"]["id"]
    invite = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": "employee-permissions@example.com"},
    )
    assert invite.status_code == 201
    accepted = client.post("/auth/employees/accept-invitation", json={
        "invitation_token": invite.json()["invitation_token"],
        "full_name": "Shop Employee",
        "password": "EmployeePass@123",
    })
    assert accepted.status_code == 201

    headers = auth(accepted.json()["access_token"])
    staff_suppliers = client.get(f"/shops/{shop_id}/distributors", headers=headers)
    assert staff_suppliers.status_code == 200

    financial = client.get(f"/shops/{shop_id}/agents/financial-position", headers=headers)
    supplier_comparison = client.get(f"/shops/{shop_id}/agents/suppliers", headers=headers)
    assert financial.status_code == 403
    assert supplier_comparison.status_code == 403


def test_supplier_cannot_receive_shop_purchase_order(client, db_session):
    owner = register_owner(client, "supplier-receive-owner@example.com")
    shop_id = owner["shop"]["id"]
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Receipt Supplier",
        "email": "supplier-cannot-receive@example.com",
        "password": "SupplierPass@123",
        "business_name": "Receipt Wholesale",
    })
    supplier_id = supplier_response.json()["supplier"]["id"]
    product = Product(
        shop_id=shop_id, name="Rice Bag", quantity=0, minimum_stock=2,
        purchase_price=500, selling_price=550, unit="bag", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    purchase = Purchase(
        shop_id=shop_id, supplier_id=supplier_id,
        invoice_number="KIRANAAI-SUPPLIER-RECEIVE", total_amount=500,
        payment_status="pending", status="ordered",
    )
    db_session.add(purchase)
    db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, product_id=product.id,
        quantity=1, unit_price=500, subtotal=500,
    )
    db_session.add(item)
    db_session.flush()

    response = client.post(
        f"/shops/{shop_id}/purchases/{purchase.id}/receive",
        headers=auth(supplier_response.json()["access_token"]),
        json={"items": [{
            "purchase_item_id": item.id,
            "batch_number": "RICE-SUPPLIER-01",
            "expiry_date": "2027-12-31",
        }]},
    )
    assert response.status_code == 403
    db_session.refresh(product)
    assert product.quantity == 0


def _create_employee(client, owner, shop_id, email):
    invite = client.post(
        f"/auth/shops/{shop_id}/employees/invitations",
        headers=auth(owner["access_token"]),
        json={"email": email},
    )
    assert invite.status_code == 201
    accepted = client.post("/auth/employees/accept-invitation", json={
        "invitation_token": invite.json()["invitation_token"],
        "full_name": "Role Test Employee",
        "password": "EmployeePass@123",
    })
    assert accepted.status_code == 201
    return accepted


def test_cashier_role_is_enforced_on_shop_staff_routes(client, db_session):
    owner = register_owner(client, "cashier-role-owner@example.com")
    shop_id = owner["shop"]["id"]
    accepted = _create_employee(client, owner, shop_id, "cashier-role@example.com")
    employee_id = accepted.json()["user"]["id"]

    assigned = client.patch(
        f"/shops/{shop_id}/employees/{employee_id}/job-role",
        headers=auth(owner["access_token"]),
        json={"job_role": "cashier"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["job_role"] == "cashier"

    headers = auth(accepted.json()["access_token"])
    assert client.get(f"/shops/{shop_id}/sales", headers=headers).status_code == 200
    assert client.get(f"/shops/{shop_id}/distributors", headers=headers).status_code == 403
    assert client.get(f"/shops/{shop_id}/purchase-orders", headers=headers).status_code == 403
    assert client.get(
        f"/shops/{shop_id}/agents/financial-position", headers=headers
    ).status_code == 403


def test_stock_manager_can_view_stock_but_not_supplier_administration(client, db_session):
    owner = register_owner(client, "stock-manager-owner@example.com")
    shop_id = owner["shop"]["id"]
    accepted = _create_employee(client, owner, shop_id, "stock-manager@example.com")
    employee_id = accepted.json()["user"]["id"]

    assigned = client.patch(
        f"/shops/{shop_id}/employees/{employee_id}/job-role",
        headers=auth(owner["access_token"]),
        json={"job_role": "stock_manager"},
    )
    assert assigned.status_code == 200

    headers = auth(accepted.json()["access_token"])
    assert client.get(f"/shops/{shop_id}/inventory/batches", headers=headers).status_code == 200
    # Exact /products route and batch routes must be available to stock managers.
    product_list = client.get("/products", params={"shop_id": shop_id}, headers=headers)
    assert product_list.status_code == 200, product_list.text

    product = Product(
        shop_id=shop_id, name="Stock Manager Tea", quantity=0, minimum_stock=2,
        purchase_price=100, selling_price=120, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    created_batch = client.post(
        "/product-batches",
        params={"shop_id": shop_id},
        headers=headers,
        json={
            "product_id": product.id,
            "batch_number": "STOCK-MANAGER-001",
            "expiry_date": "2027-12-31",
            "quantity": 5,
            "purchase_price": 100,
        },
    )
    assert created_batch.status_code == 201, created_batch.text
    batch_id = created_batch.json()["batch_id"]
    verified = client.post(
        f"/product-batches/{batch_id}/verify",
        params={"shop_id": shop_id},
        headers=headers,
        json={"verified_quantity": 5},
    )
    assert verified.status_code == 200, verified.text

    assert client.delete(
        "/products/1", params={"shop_id": shop_id}, headers=headers
    ).status_code == 403
    assert client.get(f"/shops/{shop_id}/distributors", headers=headers).status_code == 403
    assert client.get(
        f"/shops/{shop_id}/agents/financial-position", headers=headers
    ).status_code == 403


def test_supplier_can_update_only_own_order_fulfilment(client, db_session):
    owner = register_owner(client, "supplier-progress-owner@example.com")
    supplier_response = client.post("/auth/register/distributor", json={
        "full_name": "Progress Supplier",
        "email": "supplier-progress@example.com",
        "password": "SupplierPass@123",
        "business_name": "Progress Wholesale",
    })
    supplier_id = supplier_response.json()["supplier"]["id"]
    product = Product(
        shop_id=owner["shop"]["id"], name="Tea", quantity=0, minimum_stock=2,
        purchase_price=100, selling_price=120, unit="kg", is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    purchase = Purchase(
        shop_id=owner["shop"]["id"], supplier_id=supplier_id,
        invoice_number="KIRANAAI-PROGRESS-001", total_amount=100,
        payment_status="pending", status="ordered",
    )
    db_session.add(purchase)
    db_session.flush()

    headers = auth(supplier_response.json()["access_token"])
    updated = client.patch(
        f"/supplier/orders/{purchase.id}/status",
        headers=headers,
        json={"status": "dispatched", "note": "Sent with today's truck", "expected_delivery_date": "2026-11-18"},
    )
    assert updated.status_code == 200, updated.text
    db_session.refresh(purchase)
    assert purchase.supplier_status == "dispatched"
    assert purchase.status == "ordered"

    received_attempt = client.patch(
        f"/supplier/orders/{purchase.id}/status",
        headers=headers,
        json={"status": "received"},
    )
    assert received_attempt.status_code == 422

    other_supplier = client.post("/auth/register/distributor", json={
        "full_name": "Other Supplier",
        "email": "other-progress@example.com",
        "password": "SupplierPass@123",
        "business_name": "Other Wholesale",
    })
    forbidden = client.patch(
        f"/supplier/orders/{purchase.id}/status",
        headers=auth(other_supplier.json()["access_token"]),
        json={"status": "delayed"},
    )
    assert forbidden.status_code == 404
    db_session.refresh(product)
    assert product.quantity == 0
