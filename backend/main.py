from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.product_batch import ProductBatch
from app.models.expiry_record import ExpiryRecord

from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse
)

app = FastAPI(
    title="KiranaAI API",
    description="Smart Inventory and Purchasing Backend",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "Welcome to KiranaAI Backend!",
        "status": "Running successfully"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "KiranaAI"
    }


# GET: View all active products
@app.get("/products", response_model=list[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.is_active == True).all()





# POST: Add a new product
@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db)
):
    product = Product(**product_data.model_dump())

    try:
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This barcode already exists"
        )


# PUT: Update an existing product
@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = product_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(product, field, value)

    try:
        db.commit()
        db.refresh(product)
        return product

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This barcode already exists"
        )


# DELETE: Delete a product
@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return {
        "message": "Product deleted successfully!"
    }


# GET: View all low-stock products
@app.get("/products/low-stock", response_model=list[ProductResponse])
def get_low_stock_products(db: Session = Depends(get_db)):

    products = db.query(Product).filter(
        Product.is_active == True,
        Product.quantity <= Product.minimum_stock
    ).all()

    return products

# GET: View stock status of all products
@app.get("/products/stock-status")
def get_stock_status(db: Session = Depends(get_db)):

    products = db.query(Product).filter(
        Product.is_active == True
    ).all()

    result = []

    for product in products:

        if product.quantity <= 0:
            status = "Out of Stock"

        elif product.quantity <= product.minimum_stock:
            status = "Low Stock"

        else:
            status = "In Stock"

        result.append({
            "id": product.id,
            "name": product.name,
            "quantity": product.quantity,
            "minimum_stock": product.minimum_stock,
            "status": status
        })

    return result







# GET: View a product by ID
@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product



# GET: Inventory Summary Dashboard
@app.get("/inventory/summary")
def get_inventory_summary(db: Session = Depends(get_db)):

    products = db.query(Product).filter(
        Product.is_active == True
    ).all()

    total_products = len(products)

    total_stock_quantity = sum(
        product.quantity for product in products
    )

    low_stock_products = [
        product for product in products
        if 0 < product.quantity <= product.minimum_stock
    ]

    out_of_stock_products = [
        product for product in products
        if product.quantity <= 0
    ]

    total_purchase_value = sum(
        product.quantity * product.purchase_price
        for product in products
    )

    return {
        "total_products": total_products,
        "total_stock_quantity": total_stock_quantity,
        "low_stock_count": len(low_stock_products),
        "out_of_stock_count": len(out_of_stock_products),
        "total_inventory_purchase_value": round(total_purchase_value, 2)
    }





# ==========================================
# STOCK MOVEMENT MANAGEMENT
# FEFO-AWARE DAMAGE AND PERSONAL USE
# ==========================================

@app.post("/stock-movements")
def create_stock_movement(
    movement_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product_id = movement_data.get("product_id")
        movement_type = movement_data.get("movement_type")
        quantity_change = float(
            movement_data.get("quantity_change", 0)
        )
        reason = movement_data.get("reason")

        allowed_types = [
            "damage",
            "personal_use",
            "adjustment"
        ]

        if movement_type == "purchase":
            raise HTTPException(
                status_code=400,
                detail="Use POST /product-batches to record purchases with batch details"
            )

        if movement_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid movement type. Use /sales for sales "
                    "and /expiry-records for disposal or supplier returns."
                )
            )

        if quantity_change == 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity change cannot be zero"
            )

        if movement_type in [
            "damage",
            "personal_use"
        ] and quantity_change > 0:
            raise HTTPException(
                status_code=400,
                detail="This movement type requires a negative quantity"
            )

        # Lock product first to maintain consistent lock order.
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        quantity_to_deduct = abs(quantity_change)

        quantity_before = product.quantity
        quantity_after = quantity_before + quantity_change

        if quantity_after < 0:
            raise HTTPException(
                status_code=400,
                detail="Insufficient main inventory stock"
            )

        # Get all batches in FEFO order.
        batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product.id,
            ProductBatch.quantity > 0
        ).order_by(
            ProductBatch.expiry_date.asc(),
            ProductBatch.id.asc()
        ).with_for_update().all()

        batch_deductions = []

        if batches:

            # Do not allow stock changes when batch totals
            # and main inventory are already inconsistent.
            total_batch_stock = sum(
                batch.quantity for batch in batches
            )

            if abs(total_batch_stock - quantity_before) > 0.000001:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Batch stock does not match main inventory. "
                        "Reconcile inventory before processing this movement."
                    )
                )

            # Adjustments must use the dedicated reconciliation process.
            if movement_type == "adjustment":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Products with batches must use "
                        "/inventory/reconcile-batches for adjustments."
                    )
                )

            if quantity_to_deduct > total_batch_stock:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient batch stock"
                )

            remaining_quantity = quantity_to_deduct

            # Deduct from earliest-expiring batches first.
            for batch in batches:

                if remaining_quantity <= 0:
                    break

                deduction = min(
                    batch.quantity,
                    remaining_quantity
                )

                batch.quantity -= deduction
                remaining_quantity -= deduction

                batch_deductions.append({
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "quantity_deducted": deduction,
                    "remaining_batch_quantity": batch.quantity
                })

        # Update main product inventory.
        product.quantity = quantity_after

        movement = StockMovement(
            product_id=product.id,
            movement_type=movement_type,
            quantity_change=quantity_change,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=reason
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)

        return {
            "message": "Stock movement recorded successfully",
            "product_name": product.name,
            "movement_type": movement_type,
            "quantity_before": quantity_before,
            "quantity_after": product.quantity,
            "batch_deductions": batch_deductions,
            "movement": {
                "id": movement.id,
                "movement_type": movement.movement_type,
                "quantity_change": movement.quantity_change,
                "quantity_before": movement.quantity_before,
                "quantity_after": movement.quantity_after,
                "reason": movement.reason
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid movement data"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to record stock movement"
        )




    # GET: View stock movement history
@app.get("/stock-movements")
def get_stock_movements(
    product_id: int = None,
    db: Session = Depends(get_db)
):
    query = db.query(StockMovement)

    # Filter by product ID if provided
    if product_id is not None:
        query = query.filter(
            StockMovement.product_id == product_id
        )

    movements = query.order_by(
        StockMovement.created_at.desc()
    ).all()

    return [
        {
            "id": movement.id,
            "product_id": movement.product_id,
            "movement_type": movement.movement_type,
            "quantity_change": movement.quantity_change,
            "quantity_before": movement.quantity_before,
            "quantity_after": movement.quantity_after,
            "reason": movement.reason,
            "created_at": movement.created_at
        }
        for movement in movements
    ]

from datetime import date, timedelta, datetime, timezone
from fastapi import Body

# POST: Create a product batch
@app.post("/product-batches")
def create_product_batch(
    batch_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == batch_data.get("product_id"),
        Product.is_active == True
    ).with_for_update().first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    try:
        expiry_date = date.fromisoformat(
            batch_data["expiry_date"]
        )

        manufacturing_date = batch_data.get(
            "manufacturing_date"
        )

        if manufacturing_date:
            manufacturing_date = date.fromisoformat(
                manufacturing_date
            )

        quantity = float(batch_data.get("quantity", 0))
        purchase_price = float(
            batch_data.get("purchase_price", 0)
        )

        if expiry_date < date.today():
            raise HTTPException(
                status_code=400,
                detail="Cannot add an already expired batch"
            )

        if manufacturing_date and manufacturing_date > expiry_date:
            raise HTTPException(
                status_code=400,
                detail="Manufacturing date cannot be after expiry date"
            )

        if quantity <= 0 or purchase_price < 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid quantity or purchase price"
            )

        if not batch_data.get("batch_number"):
            raise HTTPException(
                status_code=400,
                detail="Batch number is required"
            )

        quantity_before = product.quantity
        quantity_after = quantity_before + quantity

        batch = ProductBatch(
            product_id=product.id,
            batch_number=batch_data["batch_number"],
            manufacturing_date=manufacturing_date,
            expiry_date=expiry_date,
            quantity=quantity,
            purchase_price=purchase_price
        )

        movement = StockMovement(
            product_id=product.id,
            movement_type="purchase",
            quantity_change=quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=f"New batch received: {batch_data['batch_number']}"
        )

        product.quantity = quantity_after

        db.add(batch)
        db.add(movement)
        db.commit()
        db.refresh(batch)

        return {
            "message": "Product batch created successfully!",
            "batch_id": batch.id,
            "product_name": product.name,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date,
            "batch_quantity": batch.quantity,
            "previous_stock": quantity_before,
            "updated_stock": product.quantity
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, KeyError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid batch data or date format"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create product batch"
        )

# GET: View product batches
@app.get("/product-batches")
def get_product_batches(
    product_id: int = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProductBatch)

    if product_id is not None:
        query = query.filter(
            ProductBatch.product_id == product_id
        )

    batches = query.order_by(
        ProductBatch.expiry_date.asc()
    ).all()

    return batches

# GET: View product batches
@app.get("/product-batches")
def get_product_batches(
    product_id: int = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProductBatch)

    if product_id is not None:
        query = query.filter(
            ProductBatch.product_id == product_id
        )

    batches = query.order_by(
        ProductBatch.expiry_date.asc()
    ).all()

    return batches

# GET: Product Expiry Alerts
@app.get("/product-batches/expiry-alerts")
def get_expiry_alerts(
    days: int = 30,
    db: Session = Depends(get_db)
):
    if days < 1:
        raise HTTPException(
            status_code=400,
            detail="Days must be at least 1"
        )

    today = date.today()
    alert_date = today + timedelta(days=days)

    batches = db.query(ProductBatch).filter(
        ProductBatch.quantity > 0,
        ProductBatch.expiry_date <= alert_date
    ).order_by(
        ProductBatch.expiry_date.asc()
    ).all()

    result = []

    for batch in batches:
        product = db.query(Product).filter(
            Product.id == batch.product_id
        ).first()

        if batch.expiry_date < today:
            status = "Expired"
        else:
            status = "Expiring Soon"

        result.append({
            "batch_id": batch.id,
            "product_id": batch.product_id,
            "product_name": product.name if product else "Unknown",
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date,
            "days_remaining": (batch.expiry_date - today).days,
            "status": status
        })

    return result





# ==========================================
# SALEABLE STOCK CALCULATION
# ==========================================

@app.get("/inventory/saleable-stock/{product_id}")
def get_saleable_stock(
    product_id: int,
    db: Session = Depends(get_db)
):
    try:
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        today = date.today()

        batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product_id,
            ProductBatch.quantity > 0,
            ProductBatch.is_verified == True,
            ProductBatch.expiry_date >= today
        ).order_by(
            ProductBatch.expiry_date.asc(),
            ProductBatch.id.asc()
        ).all()

        saleable_quantity = sum(
            batch.quantity for batch in batches
        )

        batch_details = []

        for batch in batches:
            batch_details.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "available_quantity": batch.quantity,
                "status": "Saleable"
            })

        return {
            "product_id": product.id,
            "product_name": product.name,
            "unit": product.unit,
            "total_inventory": product.quantity,
            "saleable_stock": saleable_quantity,
            "non_saleable_stock": (
                product.quantity - saleable_quantity
            ),
            "batches": batch_details
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate saleable stock"
        )








# ==========================================
# EXPIRY DISPOSAL AND SUPPLIER RETURNS
# ==========================================

@app.post("/expiry-records")
def create_expiry_record(
    expiry_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        batch_id = expiry_data.get("batch_id")
        quantity = float(expiry_data.get("quantity", 0))
        action = expiry_data.get("action")
        reason = expiry_data.get("reason")

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than zero"
            )

        if action not in ["disposal", "supplier_return"]:
            raise HTTPException(
                status_code=400,
                detail="Action must be disposal or supplier_return"
            )

        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        product = db.query(Product).filter(
            Product.id == batch.product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        if batch.expiry_date >= date.today():
            raise HTTPException(
                status_code=400,
                detail="This batch has not expired yet"
            )

        if quantity > batch.quantity:
            raise HTTPException(
                status_code=400,
                detail="Quantity exceeds available batch stock"
            )

        if quantity > product.quantity:
            raise HTTPException(
                status_code=400,
                detail="Quantity exceeds main inventory stock"
            )

        previous_stock = product.quantity

        batch.quantity -= quantity
        product.quantity -= quantity

        # Record the actual expiry action
        movement = StockMovement(
            product_id=product.id,
            movement_type=action,
            quantity_change=-quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason=f"{action}: {reason or 'Expired batch'}"
        )

        record = ExpiryRecord(
            batch_id=batch.id,
            quantity=quantity,
            action=action,
            reason=reason
        )

        db.add(movement)
        db.add(record)

        db.commit()
        db.refresh(record)

        return {
            "message": "Expiry action recorded successfully",
            "record_id": record.id,
            "product_name": product.name,
            "batch_number": batch.batch_number,
            "action": action,
            "movement_type": action,
            "quantity_processed": quantity,
            "remaining_batch_quantity": batch.quantity,
            "remaining_product_stock": product.quantity
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid expiry record data"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process expiry record"
        )




    # GET: View expiry record history
@app.get("/expiry-records")
def get_expiry_records(
    batch_id: int = None,
    db: Session = Depends(get_db)
):
    query = db.query(ExpiryRecord)

    if batch_id is not None:
        query = query.filter(
            ExpiryRecord.batch_id == batch_id
        )

    records = query.order_by(
        ExpiryRecord.recorded_at.desc()
    ).all()

    return records




    # ==========================================
# FEFO SALES MANAGEMENT
# First Expired, First Out
# ==========================================



# ==========================================
# FEFO SALES MANAGEMENT
# ==========================================

@app.post("/sales")
def create_sale(
    sale_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    product_id = sale_data.get("product_id")

    try:
        sale_quantity = float(sale_data.get("quantity", 0))

        if sale_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Sale quantity must be greater than zero"
            )

        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        if sale_quantity > product.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient main inventory stock"
            )

        # Only verified, unexpired batches are eligible.
        batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product_id,
            ProductBatch.quantity > 0,
            ProductBatch.is_verified == True,
            ProductBatch.expiry_date >= date.today()
        ).order_by(
            ProductBatch.expiry_date.asc(),
            ProductBatch.id.asc()
        ).with_for_update().all()

        available_stock = sum(
            batch.quantity for batch in batches
        )

        if sale_quantity > available_stock:
            raise HTTPException(
                status_code=400,
                detail="Insufficient verified, unexpired batch stock"
            )

        remaining = sale_quantity
        batch_updates = []

        for batch in batches:
            if remaining <= 0:
                break

            sold = min(batch.quantity, remaining)

            batch.quantity -= sold
            remaining -= sold

            batch_updates.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "quantity_sold": sold,
                "remaining_batch_quantity": batch.quantity
            })

        quantity_before = product.quantity
        product.quantity -= sale_quantity

        movement = StockMovement(
            product_id=product.id,
            movement_type="sale",
            quantity_change=-sale_quantity,
            quantity_before=quantity_before,
            quantity_after=product.quantity,
            reason="FEFO sale from verified batches"
        )

        db.add(movement)
        db.commit()

        return {
            "message": "FEFO sale completed successfully",
            "product_name": product.name,
            "quantity_sold": sale_quantity,
            "remaining_stock": product.quantity,
            "batch_updates": batch_updates
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid sale data"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process sale"
        )
# ==========================================
# STOCK RECONCILIATION
# ==========================================

@app.post("/inventory/reconcile-batches")
def reconcile_batch_stock(
    reconciliation_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    product_id = reconciliation_data.get("product_id")
    batch_quantities = reconciliation_data.get("batches")

    if not isinstance(batch_quantities, list) or not batch_quantities:
        raise HTTPException(
            status_code=400,
            detail="Batch quantities are required"
        )

    try:
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Validate all entries before changing anything.
        validated = {}
        for item in batch_quantities:
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Each batch entry must be an object"
                )

            batch_id = item.get("batch_id")
            quantity = float(item.get("quantity", -1))

            if batch_id is None or quantity < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid batch ID or quantity"
                )

            if batch_id in validated:
                raise HTTPException(
                    status_code=400,
                    detail="Duplicate batch ID"
                )

            validated[batch_id] = quantity

        batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product.id,
            ProductBatch.id.in_(validated.keys())
        ).with_for_update().all()

        if len(batches) != len(validated):
            raise HTTPException(
                status_code=400,
                detail="One or more batches do not belong to this product"
            )

        # Only after every entry is validated, apply changes.
        old_product_quantity = product.quantity
        total_quantity = 0
        updates = []

        for batch in batches:
            old_quantity = batch.quantity
            new_quantity = validated[batch.id]

            batch.quantity = new_quantity
            total_quantity += new_quantity

            updates.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "previous_quantity": old_quantity,
                "verified_quantity": new_quantity,
                "difference": new_quantity - old_quantity
            })

        product.quantity = total_quantity

        movement = StockMovement(
            product_id=product.id,
            movement_type="adjustment",
            quantity_change=total_quantity - old_product_quantity,
            quantity_before=old_product_quantity,
            quantity_after=total_quantity,
            reason="Verified batch stock reconciliation"
        )

        db.add(movement)
        db.commit()

        return {
            "message": "Batch reconciliation completed",
            "product_name": product.name,
            "previous_product_stock": old_product_quantity,
            "verified_product_stock": total_quantity,
            "batch_updates": updates
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, TypeError, AttributeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid reconciliation data"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Reconciliation failed"
        )




    # ==========================================
# BATCH VERIFICATION API
# ==========================================

@app.post("/product-batches/{batch_id}/verify")
def verify_product_batch(
    batch_id: int,
    verification_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        verified_quantity = float(
            verification_data.get("verified_quantity", -1)
        )

        if verified_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Verified quantity cannot be negative"
            )

        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        product = db.query(Product).filter(
            Product.id == batch.product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        old_batch_quantity = batch.quantity
        old_product_quantity = product.quantity

        difference = verified_quantity - old_batch_quantity
        updated_product_quantity = old_product_quantity + difference

        if updated_product_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid stock adjustment"
            )

        batch.quantity = verified_quantity
        batch.is_verified = True
        batch.verified_at = datetime.now(timezone.utc)

        product.quantity = updated_product_quantity

        movement = StockMovement(
            product_id=product.id,
            movement_type="adjustment",
            quantity_change=difference,
            quantity_before=old_product_quantity,
            quantity_after=updated_product_quantity,
            reason=f"Batch {batch.batch_number} physical verification"
        )

        db.add(movement)
        db.commit()
        db.refresh(batch)

        return {
            "message": "Batch verified successfully",
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "previous_batch_quantity": old_batch_quantity,
            "verified_quantity": batch.quantity,
            "previous_product_stock": old_product_quantity,
            "updated_product_stock": product.quantity,
            "is_verified": batch.is_verified,
            "verified_at": batch.verified_at
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid verification quantity"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to verify batch"
        )
    


    # ==========================================
# TEST-ONLY EXPIRED BATCH CREATION
# ==========================================

@app.post("/test/create-expired-batch")
def create_test_expired_batch(
    batch_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product_id = batch_data.get("product_id")
        quantity = float(batch_data.get("quantity", 0))
        expiry_date = date.fromisoformat(
            batch_data["expiry_date"]
        )

        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        if expiry_date >= date.today():
            raise HTTPException(
                status_code=400,
                detail="Test batch expiry date must be in the past"
            )

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than zero"
            )

        batch = ProductBatch(
            product_id=product.id,
            batch_number=batch_data["batch_number"],
            manufacturing_date=None,
            expiry_date=expiry_date,
            quantity=quantity,
            purchase_price=float(
                batch_data.get("purchase_price", 0)
            ),
            is_verified=True,
            verified_at=datetime.now(timezone.utc)
        )

        db.add(batch)
        db.commit()
        db.refresh(batch)

        return {
            "message": "Test expired batch created",
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date,
            "main_product_stock_unchanged": product.quantity
        }

    except HTTPException:
        db.rollback()
        raise

    except (ValueError, KeyError, TypeError):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid test batch data"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create test batch"
        )