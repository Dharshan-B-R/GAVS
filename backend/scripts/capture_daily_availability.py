"""Daily availability snapshot command for cron or a deployment scheduler.

Run from the backend directory after applying the Alembic migrations:
    python -m scripts.capture_daily_availability

The command is idempotent per shop/product/local date and never changes inventory.
"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database import SessionLocal
from app.models.shop import Shop
from app.models.product import Product
from app.models.inventory_availability_snapshot import InventoryAvailabilitySnapshot
from app.services.inventory_intelligence_service import _saleable_subquery


def capture_all_shops() -> dict:
    db = SessionLocal()
    shops_done = 0
    products_done = 0
    failures = []
    try:
        shops = db.query(Shop).filter(Shop.is_active.is_(True)).order_by(Shop.id.asc()).all()
        for shop in shops:
            try:
                try:
                    local_today = datetime.now(ZoneInfo(shop.timezone or "Asia/Kolkata")).date()
                except ZoneInfoNotFoundError as error:
                    raise ValueError(f"Invalid timezone for shop {shop.id}: {shop.timezone}") from error

                saleable = _saleable_subquery(db, shop.id)
                products = db.query(Product).filter(
                    Product.shop_id == shop.id,
                    Product.is_active.is_(True),
                ).order_by(Product.id.asc()).all()

                for product in products:
                    quantity = db.query(saleable.c.saleable_stock).filter(
                        saleable.c.product_id == product.id
                    ).scalar()
                    available_quantity = max(float(quantity or 0), 0.0)
                    snapshot = db.query(InventoryAvailabilitySnapshot).filter(
                        InventoryAvailabilitySnapshot.shop_id == shop.id,
                        InventoryAvailabilitySnapshot.product_id == product.id,
                        InventoryAvailabilitySnapshot.snapshot_date == local_today,
                    ).first()
                    if snapshot is None:
                        snapshot = InventoryAvailabilitySnapshot(
                            shop_id=shop.id,
                            product_id=product.id,
                            snapshot_date=local_today,
                            available_quantity=available_quantity,
                            is_available=available_quantity > 0,
                        )
                        db.add(snapshot)
                    else:
                        snapshot.available_quantity = available_quantity
                        snapshot.is_available = available_quantity > 0
                    products_done += 1
                db.commit()
                shops_done += 1
            except Exception as error:
                db.rollback()
                failures.append({"shop_id": shop.id, "error": str(error)})
        return {
            "shops_captured": shops_done,
            "products_captured": products_done,
            "failed_shops": failures,
        }
    finally:
        db.close()


if __name__ == "__main__":
    result = capture_all_shops()
    print(result)
    if result["failed_shops"]:
        raise SystemExit(1)
