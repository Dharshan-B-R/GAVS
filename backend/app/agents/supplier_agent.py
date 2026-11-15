"""Supplier matching agent: deterministic comparison of connected suppliers."""
from sqlalchemy.orm import Session
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.supplier import Supplier


def compare_suppliers(db: Session, shop_id: int) -> dict:
    rows = db.query(Supplier).join(
        ShopDistributorConnection,
        ShopDistributorConnection.supplier_id == Supplier.id,
    ).filter(
        ShopDistributorConnection.shop_id == shop_id,
        ShopDistributorConnection.is_active.is_(True),
        Supplier.is_active.is_(True),
    ).order_by(Supplier.name.asc()).all()
    return {"shop_id": shop_id, "count": len(rows), "suppliers": [
        {"supplier_id": s.id, "name": s.name, "contact_person": s.contact_person,
         "phone": s.phone, "email": s.email, "address": s.address}
        for s in rows
    ], "limitations": ["Supplier prices, minimum order quantities and lead times are not currently stored consistently; no price ranking is inferred."]}
