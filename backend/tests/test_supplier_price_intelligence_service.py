"""Tests for shop-scoped supplier price comparisons."""
import pytest

from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.services.supplier_price_intelligence_service import compare_supplier_prices


def _purchase(db, shop_id, product, supplier, price, quantity):
    purchase = Purchase(
        shop_id=shop_id, supplier_id=supplier.id, status="received",
        total_amount=price * quantity, payment_status="pending",
    )
    db.add(purchase)
    db.flush()
    db.add(PurchaseItem(
        purchase_id=purchase.id, product_id=product.id,
        quantity=quantity, unit_price=price, subtotal=price * quantity,
    ))


def test_supplier_prices_compare_weighted_average_per_shop(db_session):
    db_session.add(Shop(id=1, name="Price Shop"))
    db_session.flush()
    product = Product(
        shop_id=1, name="Rice", category="Grocery", quantity=20,
        minimum_stock=2, purchase_price=10, selling_price=15,
        unit="kg", is_active=True,
    )
    supplier_a = Supplier(name="Supplier A", is_active=True)
    supplier_b = Supplier(name="Supplier B", is_active=True)
    db_session.add_all([product, supplier_a, supplier_b])
    db_session.flush()
    _purchase(db_session, 1, product, supplier_a, 10, 10)
    _purchase(db_session, 1, product, supplier_a, 12, 10)
    _purchase(db_session, 1, product, supplier_b, 11, 5)
    db_session.flush()

    result = compare_supplier_prices(db_session, 1)
    row = result["products"][0]
    by_id = {s["supplier_id"]: s for s in row["suppliers"]}

    assert row["supplier_count"] == 2
    assert by_id[supplier_a.id]["weighted_average_unit_price"] == 11
    assert by_id[supplier_b.id]["weighted_average_unit_price"] == 11
    assert row["price_spread"] == 0


def test_supplier_prices_exclude_other_shop_purchases(db_session):
    db_session.add_all([Shop(id=1, name="One"), Shop(id=2, name="Two")])
    db_session.flush()
    p1 = Product(shop_id=1, name="Rice", quantity=1, minimum_stock=0, purchase_price=1, selling_price=2, unit="kg", is_active=True)
    p2 = Product(shop_id=2, name="Rice", quantity=1, minimum_stock=0, purchase_price=1, selling_price=2, unit="kg", is_active=True)
    supplier = Supplier(name="Shared supplier", is_active=True)
    db_session.add_all([p1, p2, supplier])
    db_session.flush()
    _purchase(db_session, 1, p1, supplier, 10, 1)
    _purchase(db_session, 2, p2, supplier, 99, 1)
    db_session.flush()

    result = compare_supplier_prices(db_session, 1)
    assert len(result["products"]) == 1
    assert result["products"][0]["suppliers"][0]["weighted_average_unit_price"] == 10


@pytest.mark.parametrize("limit", [0, 501])
def test_supplier_price_limit_validation(db_session, limit):
    with pytest.raises(ValueError):
        compare_supplier_prices(db_session, 1, limit)
