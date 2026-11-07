from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.batch_verification import BatchVerification
from app.models.supplier import Supplier
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_payment import PurchasePayment
from app.models.customer import Customer
from app.models.khata_transaction import KhataTransaction

from app.database import Base, engine, get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.product_batch import ProductBatch
from app.models.expiry_record import ExpiryRecord
from datetime import date, timedelta, datetime, timezone
import math
import traceback
from sqlalchemy import func, case
from decimal import Decimal


from app.schemas.purchase import (
    PurchaseCreate,
    PurchaseResponse,
    PurchaseItemCreate,
    PurchaseItemResponse
)

from app.schemas.khata_transaction import (
    KhataTransactionCreate,
    KhataTransactionResponse
)

from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse
)

# Purchase payment validation schemas
from app.schemas.purchase_payment import (
    PurchasePaymentCreate,
    PurchasePaymentResponse,
    PaymentMethod
)
# ---------------------------------------------------------
# DATABASE INITIALIZATION
# Purpose:
# Creates database tables for all registered SQLAlchemy models
# when the application starts.
# ---------------------------------------------------------

Base.metadata.create_all(bind=engine)





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
# PURCHASE AND BATCH CREATION
# ==========================================

@app.post("/product-batches", status_code=201)
def create_product_batch(
    batch_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product_id = batch_data.get("product_id")
        batch_number = batch_data.get("batch_number")
        expiry_date_input = batch_data.get("expiry_date")

        # Validate product ID
        if (
            not isinstance(product_id, int)
            or isinstance(product_id, bool)
            or product_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid product ID"
            )

        # Validate batch number
        if (
            not isinstance(batch_number, str)
            or not batch_number.strip()
            or len(batch_number) > 100
        ):
            raise HTTPException(
                status_code=400,
                detail="Valid batch number is required"
            )

        # Validate expiry date
        try:
            expiry_date = date.fromisoformat(expiry_date_input)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Expiry date must use YYYY-MM-DD format"
            )

        if expiry_date < date.today():
            raise HTTPException(
                status_code=400,
                detail="Cannot purchase an already expired batch"
            )

        # Validate quantity
        try:
            quantity = float(batch_data.get("quantity", 0))
            purchase_price = float(
                batch_data.get("purchase_price", 0)
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid quantity or purchase price"
            )

        if not math.isfinite(quantity) or quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be a valid positive number"
            )

        if (
            not math.isfinite(purchase_price)
            or purchase_price < 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Purchase price must be a valid non-negative number"
            )

        # Validate audit information
        performed_by = batch_data.get("performed_by")
        reference_type = batch_data.get(
            "reference_type", "purchase"
        )
        reference_id = batch_data.get("reference_id")

        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by user ID"
            )

        if reference_type is not None and (
            not isinstance(reference_type, str)
            or not reference_type.strip()
            or len(reference_type) > 50
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_type"
            )

        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_id"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Check existing batch and product stock consistency
        existing_batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product.id,
            ProductBatch.quantity > 0
        ).order_by(
            ProductBatch.id.asc()
        ).with_for_update().all()

        total_batch_stock = sum(
            batch.quantity for batch in existing_batches
        )

        if abs(total_batch_stock - product.quantity) > 0.000001:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Existing batch stock does not match main inventory. "
                    "Reconcile inventory before recording this purchase."
                )
            )

        previous_stock = product.quantity

        # Create new batch
        batch = ProductBatch(
            product_id=product.id,
            batch_number=batch_number.strip(),
            manufacturing_date=None,
            expiry_date=expiry_date,
            quantity=quantity,
            purchase_price=purchase_price,
            is_verified=False
        )

        # Update main inventory
        product.quantity += quantity

        # Create purchase stock movement
        movement = StockMovement(
            product_id=product.id,
            movement_type="purchase",
            quantity_change=quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason=f"Purchase of batch {batch_number}",
            performed_by=performed_by,
            reference_type=reference_type,
            reference_id=reference_id
        )

        db.add(batch)
        db.add(movement)

        # Save everything together
        db.commit()

        db.refresh(batch)
        db.refresh(movement)

        return {
            "message": "Purchase and batch recorded successfully",
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date,
            "quantity_added": quantity,
            "purchase_price": purchase_price,
            "is_verified": batch.is_verified,
            "previous_stock": previous_stock,
            "updated_stock": product.quantity,
            "movement_id": movement.id,
            "audit": {
                "performed_by": movement.performed_by,
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to record purchase and batch"
        )




# ==========================================
# GET STOCK MOVEMENT AUDIT HISTORY
# ==========================================

@app.get("/stock-movements")
def get_stock_movement_history(
    product_id: int = None,
    movement_type: str = None,
    performed_by: int = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    try:
        # Validate filters
        if product_id is not None and product_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid product ID"
            )

        if performed_by is not None and performed_by <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by user ID"
            )

        if limit < 1 or limit > 200:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 200"
            )

        # Build history query
        query = db.query(
            StockMovement,
            Product.name.label("product_name")
        ).join(
            Product,
            StockMovement.product_id == Product.id
        )

        if product_id is not None:
            query = query.filter(
                StockMovement.product_id == product_id
            )

        if movement_type is not None:
            query = query.filter(
                StockMovement.movement_type == movement_type
            )

        if performed_by is not None:
            query = query.filter(
                StockMovement.performed_by == performed_by
            )

        movements = query.order_by(
            StockMovement.created_at.desc(),
            StockMovement.id.desc()
        ).limit(limit).all()

        history = []

        for movement, product_name in movements:
            history.append({
                "movement_id": movement.id,
                "product_id": movement.product_id,
                "product_name": product_name,
                "movement_type": movement.movement_type,
                "quantity_change": movement.quantity_change,
                "quantity_before": movement.quantity_before,
                "quantity_after": movement.quantity_after,
                "reason": movement.reason,
                "performed_by": movement.performed_by,
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id,
                "created_at": movement.created_at
            })

        return {
            "total_records": len(history),
            "filters": {
                "product_id": product_id,
                "movement_type": movement_type,
                "performed_by": performed_by,
                "limit": limit
            },
            "history": history
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve stock movement history"
        )


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

        # Fetch all positive-quantity batches
        all_batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product_id,
            ProductBatch.quantity > 0
        ).order_by(
            ProductBatch.expiry_date.asc(),
            ProductBatch.id.asc()
        ).all()

        # Calculate total batch stock
        total_batch_stock = sum(
            batch.quantity for batch in all_batches
        )

        # Check consistency
        stock_difference = (
            product.quantity - total_batch_stock
        )

        is_consistent = abs(stock_difference) <= 0.000001

        # Categorize stock
        saleable_stock = 0
        expired_stock = 0
        unverified_stock = 0
        other_non_saleable_stock = 0

        batch_details = []

        for batch in all_batches:

            if batch.expiry_date < today:
                status = "Expired"
                expired_stock += batch.quantity

            elif not batch.is_verified:
                status = "Unverified"
                unverified_stock += batch.quantity

            else:
                status = "Saleable"
                saleable_stock += batch.quantity

            batch_details.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "available_quantity": batch.quantity,
                "is_verified": batch.is_verified,
                "status": status
            })

        # Remaining stock not explained by batch records
        other_non_saleable_stock = max(
            0,
            product.quantity - total_batch_stock
        )

        return {
            "product_id": product.id,
            "product_name": product.name,
            "unit": product.unit,

            "total_inventory": product.quantity,
            "total_batch_stock": total_batch_stock,

            "saleable_stock": saleable_stock,
            "expired_stock": expired_stock,
            "unverified_stock": unverified_stock,
            "other_non_saleable_stock": other_non_saleable_stock,

            "batch_stock_difference": stock_difference,
            "is_batch_stock_consistent": is_consistent,

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
# EXPIRY RECORD AND SUPPLIER RETURN API
# Purpose:
# 1. Record disposal of expired stock
# 2. Create supplier return requests
# 3. Link returns with registered suppliers
# 4. Reserve stock without immediate deduction
#
# Method: POST
# Endpoint: /expiry-records
# ==========================================

@app.post("/expiry-records")
def create_expiry_record(
    expiry_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        batch_id = expiry_data.get("batch_id")
        action = expiry_data.get("action")
        reason = expiry_data.get("reason")

        performed_by = expiry_data.get("performed_by")
        reference_type = expiry_data.get("reference_type", action)
        reference_id = expiry_data.get("reference_id")

        supplier_id = expiry_data.get("supplier_id")
        supplier_reference = expiry_data.get("supplier_reference")

        # Validate batch ID
        if (
            not isinstance(batch_id, int)
            or isinstance(batch_id, bool)
            or batch_id <= 0
        ):
            raise HTTPException(400, "Invalid batch ID")

        # Validate quantity
        try:
            quantity = float(expiry_data.get("quantity", 0))
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid quantity")

        if not math.isfinite(quantity) or quantity <= 0:
            raise HTTPException(
                400,
                "Quantity must be greater than zero"
            )

        # Validate action
        if action not in ["disposal", "supplier_return"]:
            raise HTTPException(
                400,
                "Action must be disposal or supplier_return"
            )

        # Validate reason
        if reason is not None and (
            not isinstance(reason, str) or len(reason) > 255
        ):
            raise HTTPException(400, "Invalid reason")

        # Validate audit information
        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(400, "Invalid performed_by value")

        if reference_type is not None and (
            not isinstance(reference_type, str)
            or not reference_type.strip()
            or len(reference_type) > 50
        ):
            raise HTTPException(400, "Invalid reference_type")

        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(400, "Invalid reference_id")

        # Validate supplier information for returns
        supplier = None

        if action == "supplier_return":

            if (
                not isinstance(supplier_id, int)
                or isinstance(supplier_id, bool)
                or supplier_id <= 0
            ):
                raise HTTPException(
                    400,
                    "A valid supplier_id is required"
                )

            if supplier_reference is not None and (
                not isinstance(supplier_reference, str)
                or len(supplier_reference) > 100
            ):
                raise HTTPException(
                    400,
                    "Invalid supplier reference"
                )

            # Find active supplier
            supplier = db.query(Supplier).filter(
                Supplier.id == supplier_id,
                Supplier.is_active == True
            ).first()

            if not supplier:
                raise HTTPException(
                    404,
                    "Supplier not found or inactive"
                )

        # Find batch
        batch_reference = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id
        ).first()

        if not batch_reference:
            raise HTTPException(404, "Batch not found")

        # Lock product first
        product = db.query(Product).filter(
            Product.id == batch_reference.product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(404, "Product not found")

        # Lock batch after product
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id,
            ProductBatch.product_id == product.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(404, "Batch not found")

        # Only expired batches can be processed
        if batch.expiry_date >= date.today():
            raise HTTPException(
                400,
                "This batch has not expired yet"
            )

        # Calculate existing return reservations
        reserved_quantity = 0.0

        if action == "supplier_return":
            open_returns = db.query(ExpiryRecord).filter(
                ExpiryRecord.batch_id == batch.id,
                ExpiryRecord.action == "supplier_return",
                ExpiryRecord.return_status.in_(
                    ["pending", "accepted"]
                )
            ).all()

            reserved_quantity = sum(
                record.quantity for record in open_returns
            )

        available_quantity = batch.quantity - reserved_quantity

        if quantity > available_quantity:
            raise HTTPException(
                400,
                "Quantity exceeds available stock after existing return reservations"
            )

        if quantity > product.quantity:
            raise HTTPException(
                400,
                "Quantity exceeds main inventory stock"
            )

        previous_stock = product.quantity

        # Create expiry record
        record = ExpiryRecord(
            batch_id=batch.id,
            supplier_id=(
                supplier.id
                if action == "supplier_return"
                else None
            ),
            quantity=quantity,
            action=action,
            reason=reason,
            supplier_name=(
                supplier.name
                if action == "supplier_return"
                else None
            ),
            supplier_reference=(
                supplier_reference
                if action == "supplier_return"
                else None
            ),
            return_status=(
                "pending"
                if action == "supplier_return"
                else "not_applicable"
            )
        )

        db.add(record)

        # Disposal: deduct stock immediately
        if action == "disposal":

            batch.quantity -= quantity
            product.quantity -= quantity

            movement = StockMovement(
                product_id=product.id,
                movement_type="disposal",
                quantity_change=-quantity,
                quantity_before=previous_stock,
                quantity_after=product.quantity,
                reason=f"Disposal: {reason or 'Expired batch'}",
                performed_by=performed_by,
                reference_type=reference_type,
                reference_id=reference_id
            )

            db.add(movement)

        # Supplier return: reserve stock only
        db.commit()
        db.refresh(record)

        response = {
            "message": (
                "Supplier return request created successfully"
                if action == "supplier_return"
                else "Expired stock disposed successfully"
            ),
            "record_id": record.id,
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "action": action,
            "quantity": quantity,
            "return_status": record.return_status,
            "supplier_id": record.supplier_id,
            "supplier_name": record.supplier_name,
            "supplier_reference": record.supplier_reference,
            "previous_stock": previous_stock,
            "current_stock": product.quantity,
            "remaining_batch_quantity": batch.quantity
        }

        if action == "supplier_return":

            response["message"] = (
                "Return request is pending supplier confirmation. "
                "Inventory has not been deducted."
            )

            response["reserved_quantity"] = (
                reserved_quantity + quantity
            )

        else:
            db.refresh(movement)

            response["movement_id"] = movement.id
            response["performed_by"] = movement.performed_by
            response["reference_type"] = movement.reference_type
            response["reference_id"] = movement.reference_id

        return response

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Expiry record error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to process expiry record"
        )


# ==========================================
# SUPPLIER RETURN RESPONSE API
# Purpose:
# 1. Process supplier acceptance or rejection
# 2. Retrieve linked supplier information
# 3. Update supplier reference details
# 4. Preserve inventory until pickup confirmation
#
# Method: PUT
# Endpoint: /expiry-records/{record_id}/supplier-response
# ==========================================

@app.put("/expiry-records/{record_id}/supplier-response")
def supplier_return_response(
    record_id: int,
    response_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        status = response_data.get("status")
        supplier_reference = response_data.get("supplier_reference")

        # Validate response status
        if status not in ["accepted", "rejected"]:
            raise HTTPException(
                status_code=400,
                detail="Status must be accepted or rejected"
            )

        # Validate supplier reference
        if supplier_reference is not None and (
            not isinstance(supplier_reference, str)
            or len(supplier_reference.strip()) == 0
            or len(supplier_reference) > 100
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid supplier reference"
            )

        # Find return record
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(
                status_code=404,
                detail="Expiry record not found"
            )

        if record_reference.action != "supplier_return":
            raise HTTPException(
                status_code=400,
                detail="This record is not a supplier return"
            )

        # Find associated batch
        batch_reference = db.query(ProductBatch).filter(
            ProductBatch.id == record_reference.batch_id
        ).first()

        if not batch_reference:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == batch_reference.product_id
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Lock batch
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_reference.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        # Lock return record
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        if record.return_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Return request is already {record.return_status}"
            )

        # Retrieve linked supplier
        supplier = None

        if record.supplier_id is not None:
            supplier = db.query(Supplier).filter(
                Supplier.id == record.supplier_id
            ).first()

            if not supplier:
                raise HTTPException(
                    status_code=404,
                    detail="Linked supplier not found"
                )

        # Update return status
        record.return_status = status

        if supplier_reference is not None:
            record.supplier_reference = supplier_reference.strip()

        if status == "accepted":
            record.approved_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(record)

        return {
            "message": f"Supplier return {status} successfully",
            "record_id": record.id,
            "supplier_id": record.supplier_id,
            "supplier_name": (
                supplier.name if supplier else record.supplier_name
            ),
            "return_status": record.return_status,
            "supplier_reference": record.supplier_reference,
            "inventory_deducted": False,
            "remaining_batch_quantity": batch.quantity,
            "remaining_product_stock": product.quantity
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Supplier response error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to update supplier response"
        )

# ==========================================
# SUPPLIER PICKUP CONFIRMATION API
# Purpose:
# 1. Confirm physical pickup of returned goods
# 2. Retrieve linked supplier information
# 3. Deduct inventory exactly once
# 4. Record stock movement for audit history
#
# Method: PUT
# Endpoint: /expiry-records/{record_id}/pickup
# ==========================================

@app.put("/expiry-records/{record_id}/pickup")
def confirm_supplier_pickup(
    record_id: int,
    pickup_data: dict = Body(default={}),
    db: Session = Depends(get_db)
):
    try:
        performed_by = pickup_data.get("performed_by")
        reference_id = pickup_data.get("reference_id")

        # Validate audit information
        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(400, "Invalid performed_by value")

        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(400, "Invalid reference_id")

        # Find return record
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(404, "Expiry record not found")

        if record_reference.action != "supplier_return":
            raise HTTPException(400, "Not a supplier return record")

        # Find batch
        batch_reference = db.query(ProductBatch).filter(
            ProductBatch.id == record_reference.batch_id
        ).first()

        if not batch_reference:
            raise HTTPException(404, "Batch not found")

        # Lock product first
        product = db.query(Product).filter(
            Product.id == batch_reference.product_id
        ).with_for_update().first()

        if not product:
            raise HTTPException(404, "Product not found")

        # Lock batch
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_reference.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(404, "Batch not found")

        # Lock return record
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        # Check return status
        if record.return_status != "accepted":
            raise HTTPException(
                409,
                "Only accepted return requests can be picked up"
            )

        # Retrieve linked supplier
        supplier = None

        if record.supplier_id is not None:
            supplier = db.query(Supplier).filter(
                Supplier.id == record.supplier_id
            ).first()

            if not supplier:
                raise HTTPException(
                    404,
                    "Linked supplier not found"
                )

        # Validate available stock
        if record.quantity > batch.quantity:
            raise HTTPException(
                409,
                "Insufficient batch stock for pickup"
            )

        if record.quantity > product.quantity:
            raise HTTPException(
                409,
                "Insufficient product stock for pickup"
            )

        previous_stock = product.quantity

        # Deduct stock exactly once
        batch.quantity -= record.quantity
        product.quantity -= record.quantity

        record.return_status = "picked_up"
        record.picked_up_at = datetime.now(timezone.utc)

        # Record stock movement
        movement = StockMovement(
            product_id=product.id,
            movement_type="supplier_return",
            quantity_change=-record.quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason=(
                f"Supplier pickup: "
                f"{supplier.name if supplier else record.supplier_name}"
            ),
            performed_by=performed_by,
            reference_type="expiry_record",
            reference_id=record.id
        )

        db.add(movement)

        db.commit()
        db.refresh(record)
        db.refresh(movement)

        return {
            "message": "Supplier pickup confirmed successfully",
            "record_id": record.id,
            "supplier_id": record.supplier_id,
            "supplier_name": (
                supplier.name if supplier else record.supplier_name
            ),
            "return_status": record.return_status,
            "quantity_returned": record.quantity,
            "movement_id": movement.id,
            "remaining_batch_quantity": batch.quantity,
            "remaining_product_stock": product.quantity,
            "picked_up_at": record.picked_up_at
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Supplier pickup error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to confirm supplier pickup"
        )


#Create the Supplier Credit API

# ---------------------------------------------------------
# API: Confirm Supplier Credit
# Method: PUT
# Endpoint: /expiry-records/{record_id}/credit
# Purpose:
# Records the credit amount received from a supplier after
# the returned goods have been picked up.
# ---------------------------------------------------------

@app.put("/expiry-records/{record_id}/credit")
def confirm_supplier_credit(
    record_id: int,
    credit_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        credit_amount = credit_data.get("credit_amount")

        # Validate credit amount
        try:
            credit_amount = float(credit_amount)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid credit amount"
            )

        if not math.isfinite(credit_amount) or credit_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Credit amount must be greater than zero"
            )

        # Find return record
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(
                status_code=404,
                detail="Return record not found"
            )

        if record_reference.action != "supplier_return":
            raise HTTPException(
                status_code=400,
                detail="This is not a supplier return"
            )

        # Lock the return record
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        # Credit is allowed only after pickup
        if record.return_status != "picked_up":
            raise HTTPException(
                status_code=409,
                detail="Supplier pickup must be confirmed before recording credit"
            )

        # Prevent duplicate credit recording
        if record.credit_amount is not None or record.credited_at is not None:
            raise HTTPException(
                status_code=409,
                detail="Supplier credit has already been recorded"
            )

        # Fetch registered supplier details
        supplier = None

        if record.supplier_id is not None:
            supplier = db.query(Supplier).filter(
                Supplier.id == record.supplier_id
            ).first()

        # Record supplier credit
        record.credit_amount = credit_amount
        record.credited_at = datetime.now(timezone.utc)
        record.return_status = "credited"

        db.commit()
        db.refresh(record)

        return {
            "message": "Supplier credit recorded successfully",
            "record_id": record.id,
            "supplier_id": record.supplier_id,
            "supplier_name": (
                supplier.name if supplier else record.supplier_name
            ),
            "quantity_returned": record.quantity,
            "credit_amount": record.credit_amount,
            "return_status": record.return_status,
            "credited_at": record.credited_at
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Supplier credit error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to record supplier credit"
        )



    # ==========================================
# FEFO SALES MANAGEMENT
# First Expired, First Out
# ==========================================



# ==========================================
# FEFO SALES MANAGEMENT
# ==========================================


import math
# ==========================================
# FEFO SALES MANAGEMENT
# ==========================================

@app.post("/sales")
def create_sale(
    sale_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product_id = sale_data.get("product_id")

        # Validate product ID
        if (
            not isinstance(product_id, int)
            or isinstance(product_id, bool)
            or product_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid product ID"
            )

        # Validate sale quantity
        try:
            sale_quantity = float(sale_data.get("quantity", 0))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid sale quantity"
            )

        if not math.isfinite(sale_quantity) or sale_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Sale quantity must be a valid positive number"
            )

        # Audit fields
        performed_by = sale_data.get("performed_by")
        reference_type = sale_data.get("reference_type", "sale")
        reference_id = sale_data.get("reference_id")

        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by user ID"
            )

        if reference_type is not None and (
            not isinstance(reference_type, str)
            or not reference_type.strip()
            or len(reference_type) > 50
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_type"
            )

        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_id"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Lock all positive-stock batches in FEFO order
        all_batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product_id,
            ProductBatch.quantity > 0
        ).order_by(
            ProductBatch.expiry_date.asc(),
            ProductBatch.id.asc()
        ).with_for_update().all()

        total_batch_stock = sum(
            batch.quantity for batch in all_batches
        )

        # Check batch consistency
        if abs(total_batch_stock - product.quantity) > 0.000001:
            raise HTTPException(
                status_code=409,
                detail="Batch stock does not match main inventory. Reconcile inventory before processing this sale."
            )

        # Only verified and unexpired batches are saleable
        today = date.today()

        eligible_batches = [
            batch for batch in all_batches
            if batch.is_verified and batch.expiry_date >= today
        ]

        available_stock = sum(
            batch.quantity for batch in eligible_batches
        )

        if sale_quantity > available_stock:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient verified, unexpired batch stock. Available: {available_stock}"
            )

        quantity_before = product.quantity

        remaining = sale_quantity
        batch_updates = []

        # FEFO deduction
        for batch in eligible_batches:

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

        if remaining > 0.000001:
            raise HTTPException(
                status_code=409,
                detail="Unable to complete FEFO batch deduction"
            )

        # Update main inventory
        product.quantity -= sale_quantity

        # Create movement with audit information
        movement = StockMovement(
            product_id=product.id,
            movement_type="sale",
            quantity_change=-sale_quantity,
            quantity_before=quantity_before,
            quantity_after=product.quantity,
            reason="FEFO sale from verified batches",
            performed_by=performed_by,
            reference_type=reference_type,
            reference_id=reference_id
        )

        db.add(movement)

        db.commit()
        db.refresh(movement)

        return {
            "message": "FEFO sale completed successfully",
            "product_id": product.id,
            "product_name": product.name,
            "quantity_sold": sale_quantity,
            "quantity_before": quantity_before,
            "remaining_stock": product.quantity,
            "available_stock_before_sale": available_stock,
            "batch_updates": batch_updates,
            "movement_id": movement.id,
            "audit": {
                "performed_by": movement.performed_by,
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process sale"
        )

# ==========================================
# STOCK RECONCILIATION - SAFE VERSION
# ==========================================

@app.post("/inventory/reconcile-batches")
def reconcile_batch_stock(
    reconciliation_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        product_id = reconciliation_data.get("product_id")
        batch_quantities = reconciliation_data.get("batches")

        # Audit information
        performed_by = reconciliation_data.get("performed_by")
        reference_type = reconciliation_data.get(
            "reference_type", "reconciliation"
        )
        reference_id = reconciliation_data.get("reference_id")

        # Validate product ID
        if (
            not isinstance(product_id, int)
            or isinstance(product_id, bool)
            or product_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="A valid product ID is required"
            )

        # Validate batch list
        if not isinstance(batch_quantities, list) or not batch_quantities:
            raise HTTPException(
                status_code=400,
                detail="All batch quantities are required"
            )

        # Validate performed_by
        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by value"
            )

        # Validate reference_type
        if reference_type is not None and (
            not isinstance(reference_type, str)
            or not reference_type.strip()
            or len(reference_type) > 50
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_type"
            )

        # Validate reference_id
        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_id"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Lock all batches belonging to this product
        all_batches = db.query(ProductBatch).filter(
            ProductBatch.product_id == product.id
        ).order_by(
            ProductBatch.id.asc()
        ).with_for_update().all()

        if not all_batches:
            raise HTTPException(
                status_code=400,
                detail="No batches exist for this product"
            )

        # Validate submitted batch quantities
        validated = {}

        for item in batch_quantities:

            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Each batch entry must be an object"
                )

            batch_id = item.get("batch_id")

            if (
                not isinstance(batch_id, int)
                or isinstance(batch_id, bool)
                or batch_id <= 0
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid batch ID"
                )

            try:
                quantity = float(item.get("quantity"))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid batch quantity"
                )

            if not math.isfinite(quantity) or quantity < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Batch quantity must be a valid non-negative number"
                )

            if batch_id in validated:
                raise HTTPException(
                    status_code=400,
                    detail="Duplicate batch ID"
                )

            validated[batch_id] = quantity

        # Require every existing batch to be included
        existing_ids = {
            batch.id for batch in all_batches
        }

        submitted_ids = set(validated.keys())

        if existing_ids != submitted_ids:
            missing_ids = sorted(existing_ids - submitted_ids)
            extra_ids = sorted(submitted_ids - existing_ids)

            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Submitted batches do not match product batches",
                    "missing_batch_ids": missing_ids,
                    "invalid_batch_ids": extra_ids
                }
            )

        # Calculate new stock before changing anything
        old_product_quantity = product.quantity

        total_quantity = sum(
            validated[batch.id] for batch in all_batches
        )

        updates = []

        for batch in all_batches:

            old_quantity = batch.quantity
            new_quantity = validated[batch.id]

            updates.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "previous_quantity": old_quantity,
                "verified_quantity": new_quantity,
                "difference": new_quantity - old_quantity
            })

        # Apply batch updates
        for batch in all_batches:
            batch.quantity = validated[batch.id]

        product.quantity = total_quantity

        difference = total_quantity - old_product_quantity

        movement_id = None

        # Record movement when stock actually changes
        if abs(difference) > 0.000001:

            movement = StockMovement(
                product_id=product.id,
                movement_type="adjustment",
                quantity_change=difference,
                quantity_before=old_product_quantity,
                quantity_after=total_quantity,
                reason="Complete batch stock reconciliation",
                performed_by=performed_by,
                reference_type=reference_type,
                reference_id=reference_id
            )

            db.add(movement)
            db.flush()

            movement_id = movement.id

        db.commit()

        return {
            "message": "Complete batch reconciliation successful",
            "product_id": product.id,
            "product_name": product.name,
            "previous_product_stock": old_product_quantity,
            "verified_product_stock": total_quantity,
            "stock_difference": difference,
            "movement_id": movement_id,
            "performed_by": performed_by,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "total_batches_reconciled": len(all_batches),
            "batch_updates": updates
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Reconciliation failed"
        )

   
# ==========================================
# BATCH VERIFICATION API - SAFE VERSION
# ==========================================

@app.post("/product-batches/{batch_id}/verify")
def verify_product_batch(
    batch_id: int,
    verification_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        if (
            not isinstance(batch_id, int)
            or isinstance(batch_id, bool)
            or batch_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid batch ID"
            )

        try:
            verified_quantity = float(
                verification_data.get("verified_quantity", -1)
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid verification quantity"
            )

        if not math.isfinite(verified_quantity) or verified_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Verified quantity must be a valid non-negative number"
            )

        reason = verification_data.get("reason")

        allow_reverification = verification_data.get(
            "allow_reverification", False
        )

        performed_by = verification_data.get("performed_by")
        reference_type = verification_data.get(
            "reference_type", "batch_verification"
        )
        reference_id = verification_data.get("reference_id")

        if not isinstance(allow_reverification, bool):
            raise HTTPException(
                status_code=400,
                detail="allow_reverification must be true or false"
            )

        if performed_by is not None and (
            not isinstance(performed_by, int)
            or isinstance(performed_by, bool)
            or performed_by <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by value"
            )

        if reference_type is not None and (
            not isinstance(reference_type, str)
            or not reference_type.strip()
            or len(reference_type) > 50
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_type"
            )

        if reference_id is not None and (
            not isinstance(reference_id, int)
            or isinstance(reference_id, bool)
            or reference_id <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid reference_id"
            )

        # Find batch
        batch_reference = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id
        ).first()

        if not batch_reference:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == batch_reference.product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        # Lock batch
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id,
            ProductBatch.product_id == product.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        if batch.is_verified and not allow_reverification:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Batch is already verified. "
                    "Set allow_reverification to true "
                    "only after confirming a new physical count."
                )
            )

        old_batch_quantity = batch.quantity
        old_product_quantity = product.quantity

        difference = verified_quantity - old_batch_quantity

        updated_product_quantity = (
            old_product_quantity + difference
        )

        if updated_product_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid stock adjustment"
            )

        # Update batch
        batch.quantity = verified_quantity
        batch.is_verified = True
        batch.verified_at = datetime.now(timezone.utc)

        # Update product stock
        product.quantity = updated_product_quantity

        movement_id = None

        # Create stock movement only when quantity changes
        if abs(difference) > 0.000001:
            movement = StockMovement(
                product_id=product.id,
                movement_type="adjustment",
                quantity_change=difference,
                quantity_before=old_product_quantity,
                quantity_after=updated_product_quantity,
                reason=(
                    f"Batch {batch.batch_number} physical verification: "
                    f"{reason or 'Quantity verification'}"
                ),
                performed_by=performed_by,
                reference_type=reference_type,
                reference_id=reference_id
            )

            db.add(movement)
            db.flush()

            movement_id = movement.id

        # Always save verification history,
        # even when the quantity difference is zero.
        verification_record = BatchVerification(
            batch_id=batch.id,
            previous_quantity=old_batch_quantity,
            verified_quantity=verified_quantity,
            performed_by=performed_by,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            allow_reverification=1 if allow_reverification else 0
            
        )

        db.add(verification_record)

        # Save everything together
        db.commit()

        db.refresh(batch)
        db.refresh(verification_record)

        return {
            "message": "Batch verified successfully",
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "previous_batch_quantity": old_batch_quantity,
            "verified_quantity": batch.quantity,
            "previous_product_stock": old_product_quantity,
            "updated_product_stock": product.quantity,
            "quantity_difference": difference,
            "movement_id": movement_id,
            "verification_history_id": verification_record.id,
            "performed_by": performed_by,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "is_verified": batch.is_verified,
            "verified_at": batch.verified_at
        }


    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("BATCH VERIFICATION ERROR:", repr(error))
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Unable to verify batch"
        )





# ==========================================
# BATCH VERIFICATION HISTORY
# ==========================================

@app.get("/batch-verifications")
def get_batch_verification_history(
    batch_id: int = None,
    performed_by: int = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    try:
        # Validate filters
        if batch_id is not None and batch_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid batch ID"
            )

        if performed_by is not None and performed_by <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid performed_by user ID"
            )

        if limit < 1 or limit > 200:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 200"
            )

        # Fetch verification history
        query = db.query(
            BatchVerification,
            ProductBatch.batch_number,
            Product.name.label("product_name")
        ).join(
            ProductBatch,
            BatchVerification.batch_id == ProductBatch.id
        ).join(
            Product,
            ProductBatch.product_id == Product.id
        )

        if batch_id is not None:
            query = query.filter(
                BatchVerification.batch_id == batch_id
            )

        if performed_by is not None:
            query = query.filter(
                BatchVerification.performed_by == performed_by
            )

        records = query.order_by(
            BatchVerification.verified_at.desc(),
            BatchVerification.id.desc()
        ).limit(limit).all()

        history = []

        for record, batch_number, product_name in records:
            history.append({
                "verification_id": record.id,
                "batch_id": record.batch_id,
                "batch_number": batch_number,
                "product_name": product_name,
                "previous_quantity": record.previous_quantity,
                "verified_quantity": record.verified_quantity,
                "quantity_difference": (
                    record.verified_quantity - record.previous_quantity
                ),
                "performed_by": record.performed_by,
                "reason": record.reason,
                "allow_reverification": bool(
                    record.allow_reverification
                ),
                "verified_at": record.verified_at
            })

        return {
            "total_records": len(history),
            "filters": {
                "batch_id": batch_id,
                "performed_by": performed_by,
                "limit": limit
            },
            "history": history
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve batch verification history"
        )

# ==========================================
# GET VERIFICATION HISTORY FOR ONE BATCH
# ==========================================

@app.get("/batch-verifications/{batch_id}")
def get_batch_verification_by_batch(
    batch_id: int,
    db: Session = Depends(get_db)
):
    try:
        if batch_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid batch ID"
            )

        # Check whether batch exists
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == batch_id
        ).first()

        if not batch:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        # Fetch verification history
        records = db.query(BatchVerification).filter(
            BatchVerification.batch_id == batch_id
        ).order_by(
            BatchVerification.verified_at.desc(),
            BatchVerification.id.desc()
        ).all()

        history = []

        for record in records:
            history.append({
                "verification_id": record.id,
                "batch_id": record.batch_id,
                "batch_number": batch.batch_number,
                "previous_quantity": record.previous_quantity,
                "verified_quantity": record.verified_quantity,
                "quantity_difference": (
                    record.verified_quantity -
                    record.previous_quantity
                ),
                "performed_by": record.performed_by,
                "reference_type": record.reference_type,
                "reference_id": record.reference_id,
                "reason": record.reason,
                "allow_reverification": bool(
                    record.allow_reverification
                ),
                "verified_at": record.verified_at
            })

        return {
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "total_verifications": len(history),
            "history": history
        }

    except HTTPException:
        raise

    except Exception as error:
        print(
            "BATCH HISTORY ERROR:",
            repr(error)
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve batch verification history"
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
        batch_number = batch_data.get("batch_number")

        if (
            not isinstance(product_id, int)
            or isinstance(product_id, bool)
            or product_id <= 0
        ):
            raise HTTPException(400, "Invalid product ID")

        if (
            not isinstance(batch_number, str)
            or not batch_number.strip()
            or len(batch_number.strip()) > 100
        ):
            raise HTTPException(400, "Invalid batch number")

        try:
            quantity = float(batch_data.get("quantity", 0))
            purchase_price = float(batch_data.get("purchase_price", 0))
            expiry_date = date.fromisoformat(batch_data["expiry_date"])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, "Invalid test batch data")

        if not math.isfinite(quantity) or quantity <= 0:
            raise HTTPException(400, "Invalid quantity")

        if not math.isfinite(purchase_price) or purchase_price < 0:
            raise HTTPException(400, "Invalid purchase price")

        if expiry_date >= date.today():
            raise HTTPException(
                400,
                "Test batch expiry date must be in the past"
            )

        product = db.query(Product).filter(
            Product.id == product_id,
            Product.is_active == True
        ).with_for_update().first()

        if not product:
            raise HTTPException(404, "Product not found")

        duplicate = db.query(ProductBatch).filter(
            ProductBatch.batch_number == batch_number.strip()
        ).first()

        if duplicate:
            raise HTTPException(
                409,
                "Batch number already exists"
            )

        previous_stock = product.quantity

        batch = ProductBatch(
            product_id=product.id,
            batch_number=batch_number.strip(),
            manufacturing_date=None,
            expiry_date=expiry_date,
            quantity=quantity,
            purchase_price=purchase_price,
            is_verified=True,
            verified_at=datetime.now(timezone.utc)
        )

        product.quantity += quantity

        movement = StockMovement(
            product_id=product.id,
            movement_type="adjustment",
            quantity_change=quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason="Test-only expired batch creation"
        )

        db.add(batch)
        db.add(movement)

        db.commit()
        db.refresh(batch)
        db.refresh(movement)

        return {
            "message": "Test expired batch created successfully",
            "product_id": product.id,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date,
            "previous_product_stock": previous_stock,
            "updated_product_stock": product.quantity,
            "movement_id": movement.id
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Test batch creation error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to create test batch"
        )





# ==========================================
# SUPPLIER REGISTRATION API
# Purpose: Register a new supplier in KiranaAI
# Method: POST
# Endpoint: /suppliers
# ==========================================

@app.post("/suppliers")
def create_supplier(
    supplier_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        name = supplier_data.get("name")
        phone = supplier_data.get("phone")
        email = supplier_data.get("email")
        gstin = supplier_data.get("gstin")

        # Validate supplier name
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(
                status_code=400,
                detail="Supplier name is required"
            )

        name = name.strip()

        if len(name) > 150:
            raise HTTPException(400, "Supplier name is too long")

        # Validate phone number
        if phone is not None:
            if not isinstance(phone, str) or len(phone) > 20:
                raise HTTPException(400, "Invalid phone number")

        # Validate email
        if email is not None:
            if not isinstance(email, str) or len(email) > 150:
                raise HTTPException(400, "Invalid email")

        # Validate GSTIN
        if gstin is not None:
            if not isinstance(gstin, str) or len(gstin) != 15:
                raise HTTPException(
                    400,
                    "GSTIN must contain 15 characters"
                )

        # Create supplier record
        supplier = Supplier(
            name=name,
            contact_person=supplier_data.get("contact_person"),
            phone=phone,
            email=email,
            address=supplier_data.get("address"),
            gstin=gstin.upper() if gstin else None,
            notes=supplier_data.get("notes")
        )

        db.add(supplier)
        db.commit()
        db.refresh(supplier)

        return {
            "message": "Supplier registered successfully",
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "phone": supplier.phone,
                "email": supplier.email,
                "address": supplier.address,
                "gstin": supplier.gstin,
                "is_active": supplier.is_active,
                "created_at": supplier.created_at
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Supplier registration error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to register supplier"
        )



# ==========================================
# GET ALL SUPPLIERS API
# Purpose: Retrieve all registered suppliers
# Method: GET
# Endpoint: /suppliers
# ==========================================

@app.get("/suppliers")
def get_all_suppliers(
    db: Session = Depends(get_db)
):
    try:
        suppliers = db.query(Supplier).order_by(
            Supplier.id.desc()
        ).all()

        return {
            "total_suppliers": len(suppliers),
            "suppliers": [
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "contact_person": supplier.contact_person,
                    "phone": supplier.phone,
                    "email": supplier.email,
                    "address": supplier.address,
                    "gstin": supplier.gstin,
                    "is_active": supplier.is_active,
                    "created_at": supplier.created_at
                }
                for supplier in suppliers
            ]
        }

    except Exception as error:
        print("Get suppliers error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve suppliers"
        )





# ==========================================
# UPDATE SUPPLIER API
# Purpose: Update an existing supplier profile
# Method: PUT
# Endpoint: /suppliers/{supplier_id}
# ==========================================

@app.put("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    supplier_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).with_for_update().first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        allowed_fields = [
            "name",
            "contact_person",
            "phone",
            "email",
            "address",
            "gstin",
            "notes"
        ]

        for field in allowed_fields:
            if field in supplier_data:
                value = supplier_data[field]

                if field == "name":
                    if not isinstance(value, str) or not value.strip():
                        raise HTTPException(
                            400,
                            "Supplier name cannot be empty"
                        )
                    value = value.strip()
                    if len(value) > 150:
                        raise HTTPException(400, "Supplier name is too long")

                elif field == "phone" and value is not None:
                    if not isinstance(value, str) or len(value) > 20:
                        raise HTTPException(400, "Invalid phone number")

                elif field == "email" and value is not None:
                    if not isinstance(value, str) or len(value) > 150:
                        raise HTTPException(400, "Invalid email")

                elif field == "gstin" and value is not None:
                    if not isinstance(value, str) or len(value) != 15:
                        raise HTTPException(400, "Invalid GSTIN")
                    value = value.upper()

                elif field in ["contact_person"] and value is not None:
                    if not isinstance(value, str) or len(value) > 150:
                        raise HTTPException(400, f"Invalid {field}")

                elif field in ["address", "notes"] and value is not None:
                    if not isinstance(value, str):
                        raise HTTPException(400, f"Invalid {field}")

                setattr(supplier, field, value)

        db.commit()
        db.refresh(supplier)

        return {
            "message": "Supplier updated successfully",
            "supplier_id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone,
            "email": supplier.email,
            "address": supplier.address,
            "gstin": supplier.gstin,
            "notes": supplier.notes,
            "is_active": supplier.is_active
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Update supplier error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to update supplier"
        )



# ==========================================
# DEACTIVATE SUPPLIER API
# Purpose: Deactivate a supplier without deleting history
# Method: PATCH
# Endpoint: /suppliers/{supplier_id}/deactivate
# ==========================================

@app.patch("/suppliers/{supplier_id}/deactivate")
def deactivate_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).with_for_update().first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        if not supplier.is_active:
            raise HTTPException(
                status_code=409,
                detail="Supplier is already inactive"
            )

        supplier.is_active = False

        db.commit()
        db.refresh(supplier)

        return {
            "message": "Supplier deactivated successfully",
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "is_active": supplier.is_active
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Deactivate supplier error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to deactivate supplier"
        )




# ==========================================
# REACTIVATE SUPPLIER API
# Purpose: Activate a previously deactivated supplier
# Method: PATCH
# Endpoint: /suppliers/{supplier_id}/reactivate
# ==========================================

@app.patch("/suppliers/{supplier_id}/reactivate")
def reactivate_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).with_for_update().first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        if supplier.is_active:
            raise HTTPException(
                status_code=409,
                detail="Supplier is already active"
            )

        supplier.is_active = True

        db.commit()
        db.refresh(supplier)

        return {
            "message": "Supplier reactivated successfully",
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "is_active": supplier.is_active
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Reactivate supplier error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to reactivate supplier"
        )

# ==========================================
# GET SUPPLIER BY ID API
# Purpose: Retrieve the complete profile of one supplier
# Method: GET
# Endpoint: /suppliers/{supplier_id}
# ==========================================

@app.get("/suppliers/{supplier_id}")
def get_supplier_by_id(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        return {
            "supplier_id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone,
            "email": supplier.email,
            "address": supplier.address,
            "gstin": supplier.gstin,
            "notes": supplier.notes,
            "is_active": supplier.is_active,
            "created_at": supplier.created_at,
            "updated_at": supplier.updated_at
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Get supplier error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve supplier"
        )




# ---------------------------------------------------------
# API: Create Supplier Purchase
# Method: POST
# Endpoint: /purchases
# Purpose:
# Creates a supplier purchase invoice with multiple products.
# Creates individual unverified batches and stock movements.
# ---------------------------------------------------------

@app.post("/purchases", response_model=PurchaseResponse)
def create_purchase(
    purchase_data: PurchaseCreate,
    db: Session = Depends(get_db)
):
    try:
        # 1. Validate active supplier
        supplier = db.query(Supplier).filter(
            Supplier.id == purchase_data.supplier_id,
            Supplier.is_active == True
        ).first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Active supplier not found"
            )

        # 2. Validate purchase items
        total_amount = 0
        validated_items = []

        for item in purchase_data.items:

            product = db.query(Product).filter(
                Product.id == item.product_id,
                Product.is_active == True
            ).with_for_update().first()

            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Active product {item.product_id} not found"
                )

            if not math.isfinite(item.unit_price):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid purchase unit price"
                )

            if not item.batch_number.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Batch number cannot be empty"
                )

            if item.expiry_date < date.today():
                raise HTTPException(
                    status_code=400,
                    detail="Cannot purchase an already expired batch"
                )

            if (
                item.manufacturing_date is not None
                and item.manufacturing_date > item.expiry_date
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Manufacturing date cannot be after expiry date"
                )

            subtotal = item.quantity * item.unit_price

            if not math.isfinite(subtotal):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid purchase subtotal"
                )

            total_amount += subtotal

            validated_items.append({
                "product": product,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": subtotal,
                "batch_number": item.batch_number.strip(),
                "manufacturing_date": item.manufacturing_date,
                "expiry_date": item.expiry_date
            })

        if not math.isfinite(total_amount):
            raise HTTPException(
                status_code=400,
                detail="Invalid purchase total"
            )

        # 3. Create purchase invoice
        purchase = Purchase(
            supplier_id=supplier.id,
            invoice_number=purchase_data.invoice_number,
            total_amount=total_amount,
            payment_status="pending",
            notes=purchase_data.notes
        )

        db.add(purchase)
        db.flush()

        # 4. Create purchase items, batches and stock movements
        for item_data in validated_items:

            product = item_data["product"]
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]

            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=item_data["subtotal"]
            )

            
            # 1. Create unverified inventory batch
            batch = ProductBatch(
                product_id=product.id,
                batch_number=item_data["batch_number"],
                manufacturing_date=item_data["manufacturing_date"],
                expiry_date=item_data["expiry_date"],
                quantity=quantity,
                purchase_price=unit_price,
                is_verified=False
            )

            db.add(batch)
            db.flush()

            # 2. Create purchase item linked to its batch
            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                batch_id=batch.id,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=item_data["subtotal"]
            )

            db.add(purchase_item)


            db.add(batch)

            # Update recorded inventory
            previous_stock = product.quantity
            product.quantity += quantity

            # Record stock movement
            movement = StockMovement(
                product_id=product.id,
                movement_type="purchase",
                quantity_change=quantity,
                quantity_before=previous_stock,
                quantity_after=product.quantity,
                reason=f"Supplier purchase #{purchase.id}",
                reference_type="purchase",
                reference_id=purchase.id
            )

            db.add(movement)

        # 5. Commit all purchase records together
        db.commit()
        db.refresh(purchase)

        return purchase

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Purchase creation error:", str(error))
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Unable to create supplier purchase"
        )




# ---------------------------------------------------------
# API: Get Purchase By ID
# Method: GET
# Endpoint: /purchases/{purchase_id}
# Purpose:
# Retrieves a purchase invoice with supplier details,
# purchased products and their linked inventory batches.
# ---------------------------------------------------------

@app.get("/purchases/{purchase_id}")
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db)
):
    try:
        # Find purchase with its items
        purchase = db.query(Purchase).filter(
            Purchase.id == purchase_id
        ).first()

        if not purchase:
            raise HTTPException(
                status_code=404,
                detail="Purchase not found"
            )

        # Fetch supplier
        supplier = db.query(Supplier).filter(
            Supplier.id == purchase.supplier_id
        ).first()

        # Prepare purchase item details
        items = []

        for item in purchase.items:
            batch = item.batch

            items.append({
                "purchase_item_id": item.id,
                "product_id": item.product_id,
                "product_name": (
                    item.product.name if item.product else None
                ),
                "batch_id": item.batch_id,
                "batch_number": (
                    batch.batch_number if batch else None
                ),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "expiry_date": (
                    batch.expiry_date if batch else None
                ),
                "is_verified": (
                    batch.is_verified if batch else None
                )
            })

        return {
            "purchase_id": purchase.id,
            "supplier_id": purchase.supplier_id,
            "supplier_name": (
                supplier.name if supplier else None
            ),
            "invoice_number": purchase.invoice_number,
            "purchase_date": purchase.purchase_date,
            "total_amount": purchase.total_amount,
            "payment_status": purchase.payment_status,
            "notes": purchase.notes,
            "items": items
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Get purchase error:", str(error))
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve purchase"
        )



# ---------------------------------------------------------
# API: Record Supplier Purchase Payment
# Method: POST
# Endpoint: /purchases/{purchase_id}/payments
# Purpose:
# Records full or partial payments against a purchase invoice.
# Prevents overpayment and updates the invoice payment status.
# ---------------------------------------------------------

@app.post("/purchases/{purchase_id}/payments")
def record_purchase_payment(
    purchase_id: int,
    payment_data: PurchasePaymentCreate,
    db: Session = Depends(get_db)
):
    try:
        # Lock purchase to prevent concurrent overpayments
        purchase = db.query(Purchase).filter(
            Purchase.id == purchase_id
        ).with_for_update().first()

        if not purchase:
            raise HTTPException(
                status_code=404,
                detail="Purchase invoice not found"
            )

        # Validate payment amount
        amount = float(payment_data.amount)

        if not math.isfinite(amount) or amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Payment amount must be greater than zero"
            )

        # Calculate previous payments
        total_paid = db.query(
            func.coalesce(
                func.sum(PurchasePayment.amount), 0
            )
        ).filter(
            PurchasePayment.purchase_id == purchase_id
        ).scalar()

        outstanding = purchase.total_amount - float(total_paid)

        # Prevent overpayment
        if amount > outstanding:
            raise HTTPException(
                status_code=409,
                detail=f"Payment exceeds outstanding balance of {outstanding:.2f}"
            )

        # Validate transaction reference for digital payments
        payment_method = payment_data.payment_method.value

        if (
            payment_method in ["upi", "bank_transfer"]
            and not payment_data.transaction_reference
        ):
            raise HTTPException(
                status_code=400,
                detail="Transaction reference is required for digital payments"
            )

        # Create payment record
        payment = PurchasePayment(
            purchase_id=purchase.id,
            amount=amount,
            payment_method=payment_method,
            transaction_reference=payment_data.transaction_reference,
            notes=payment_data.notes
        )

        db.add(payment)
        db.flush()

        # Calculate updated payment status
        updated_paid = float(total_paid) + amount
        remaining = purchase.total_amount - updated_paid

        if math.isclose(
            updated_paid,
            purchase.total_amount,
            rel_tol=1e-9,
            abs_tol=1e-7
        ):
            purchase.payment_status = "paid"
            remaining = 0.0

        elif updated_paid > 0:
            purchase.payment_status = "partially_paid"

        else:
            purchase.payment_status = "pending"

        db.commit()
        db.refresh(payment)

        return {
            "message": "Purchase payment recorded successfully",
            "payment_id": payment.id,
            "purchase_id": purchase.id,
            "payment_amount": payment.amount,
            "payment_method": payment.payment_method,
            "total_amount": purchase.total_amount,
            "total_paid": updated_paid,
            "outstanding_balance": remaining,
            "payment_status": purchase.payment_status,
            "paid_at": payment.paid_at
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Purchase payment error:", str(error))
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Unable to record purchase payment"
        )




# ============================================================
# CREATE CUSTOMER API
# Purpose: Add a new customer to the KiranaAI customer database.
# Method: POST
# Endpoint: /customers
# ============================================================

@app.post("/customers", response_model=CustomerResponse)
def create_customer(
    customer_data: CustomerCreate,
    db: Session = Depends(get_db)
):
    try:
        # Validate customer name
        customer_name = customer_data.name.strip()

        if not customer_name:
            raise HTTPException(
                status_code=400,
                detail="Customer name cannot be empty"
            )

        # Create customer object
        new_customer = Customer(
            name=customer_name,
            phone=customer_data.phone,
            address=customer_data.address,
            notes=customer_data.notes
        )

        # Save customer
        db.add(new_customer)
        db.commit()
        db.refresh(new_customer)

        return new_customer

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to create customer"
        )



# ============================================================
# GET ALL CUSTOMERS API
# Purpose: Retrieve all customers from the database.
# Method: GET
# Endpoint: /customers
# ============================================================

@app.get("/customers", response_model=list[CustomerResponse])
def get_all_customers(
    db: Session = Depends(get_db)
):
    try:
        customers = (
            db.query(Customer)
            .order_by(Customer.id.desc())
            .all()
        )

        return customers

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve customers"
        )

# ============================================================
# GET CUSTOMER BY ID API
# Purpose: Retrieve one customer using their unique ID.
# Method: GET
# Endpoint: /customers/{customer_id}
# ============================================================

@app.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer_by_id(
    customer_id: int,
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    return customer

# ============================================================
# UPDATE CUSTOMER API
# Purpose: Update an existing customer's information.
# Method: PUT
# Endpoint: /customers/{customer_id}
# ============================================================

@app.put("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db)
):
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        update_data = customer_data.model_dump(exclude_unset=True)

        if "name" in update_data:
            if not update_data["name"] or not update_data["name"].strip():
                raise HTTPException(
                    status_code=400,
                    detail="Customer name cannot be empty"
                )

            update_data["name"] = update_data["name"].strip()

        for field, value in update_data.items():
            setattr(customer, field, value)

        db.commit()
        db.refresh(customer)

        return customer

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to update customer"
        )

# ============================================================
# DEACTIVATE CUSTOMER API
# Purpose: Deactivate a customer without deleting their history.
# Method: PATCH
# Endpoint: /customers/{customer_id}/deactivate
# ============================================================

@app.patch("/customers/{customer_id}/deactivate")
def deactivate_customer(
    customer_id: int,
    db: Session = Depends(get_db)
):
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        if not customer.is_active:
            raise HTTPException(
                status_code=400,
                detail="Customer is already inactive"
            )

        customer.is_active = False

        db.commit()
        db.refresh(customer)

        return {
            "message": "Customer deactivated successfully",
            "customer_id": customer.id,
            "name": customer.name,
            "is_active": customer.is_active
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to deactivate customer"
        )

    # ============================================================
# REACTIVATE CUSTOMER API
# Purpose: Reactivate a previously deactivated customer.
# Method: PATCH
# Endpoint: /customers/{customer_id}/reactivate
# ============================================================

@app.patch("/customers/{customer_id}/reactivate")
def reactivate_customer(
    customer_id: int,
    db: Session = Depends(get_db)
):
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        if customer.is_active:
            raise HTTPException(
                status_code=400,
                detail="Customer is already active"
            )

        customer.is_active = True

        db.commit()
        db.refresh(customer)

        return {
            "message": "Customer reactivated successfully",
            "customer_id": customer.id,
            "name": customer.name,
            "is_active": customer.is_active
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to reactivate customer"
        )

    # ============================================================
# FILTER CUSTOMERS API
# Purpose: Retrieve customers based on active/inactive status.
# Method: GET
# Endpoint: /customers/status/{is_active}
# ============================================================

@app.get(
    "/customers/status/{is_active}",
    response_model=list[CustomerResponse]
)
def get_customers_by_status(
    is_active: bool,
    db: Session = Depends(get_db)
):
    try:
        customers = (
            db.query(Customer)
            .filter(Customer.is_active == is_active)
            .order_by(Customer.id.desc())
            .all()
        )

        return customers

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve customers by status"
        )



    # ============================================================
# CREATE KHATA TRANSACTION API
# Purpose: Record customer credit (Udhar) and repayments.
# Method: POST
# Endpoint: /customers/{customer_id}/khata
# ============================================================

@app.post(
    "/customers/{customer_id}/khata",
    response_model=KhataTransactionResponse
)
def create_khata_transaction(
    customer_id: int,
    transaction_data: KhataTransactionCreate,
    db: Session = Depends(get_db)
):
    try:
        # Lock customer record to prevent simultaneous balance updates
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .with_for_update()
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        if not customer.is_active:
            raise HTTPException(
                status_code=400,
                detail="Cannot record transactions for an inactive customer"
            )

        # Calculate existing customer credit
        total_credit = (
            db.query(func.coalesce(func.sum(KhataTransaction.amount), 0))
            .filter(
                KhataTransaction.customer_id == customer_id,
                KhataTransaction.transaction_type == "credit"
            )
            .scalar()
        )

        # Calculate existing repayments
        total_repayments = (
            db.query(func.coalesce(func.sum(KhataTransaction.amount), 0))
            .filter(
                KhataTransaction.customer_id == customer_id,
                KhataTransaction.transaction_type == "repayment"
            )
            .scalar()
        )

        outstanding_balance = total_credit - total_repayments

        # Prevent repayment greater than outstanding balance
        if transaction_data.transaction_type == "repayment":
            if transaction_data.amount > outstanding_balance:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Repayment exceeds outstanding balance. "
                        f"Current balance: {outstanding_balance}"
                    )
                )

        # Create Khata transaction
        new_transaction = KhataTransaction(
            customer_id=customer_id,
            transaction_type=transaction_data.transaction_type,
            amount=transaction_data.amount,
            description=transaction_data.description,
            reference_number=transaction_data.reference_number
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        return new_transaction

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to record Khata transaction"
        )


# ============================================================
# GET CUSTOMER KHATA BALANCE API
# Purpose: Calculate total credit, repayments and outstanding.
# Method: GET
# Endpoint: /customers/{customer_id}/khata/balance
# ============================================================

@app.get("/customers/{customer_id}/khata/balance")
def get_customer_khata_balance(
    customer_id: int,
    db: Session = Depends(get_db)
):
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        total_credit = (
            db.query(func.coalesce(func.sum(KhataTransaction.amount), 0))
            .filter(
                KhataTransaction.customer_id == customer_id,
                KhataTransaction.transaction_type == "credit"
            )
            .scalar()
        )

        total_repayments = (
            db.query(func.coalesce(func.sum(KhataTransaction.amount), 0))
            .filter(
                KhataTransaction.customer_id == customer_id,
                KhataTransaction.transaction_type == "repayment"
            )
            .scalar()
        )

        outstanding = total_credit - total_repayments

        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "total_credit": total_credit,
            "total_repayments": total_repayments,
            "outstanding_balance": outstanding
        }

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to calculate customer Khata balance"
        )


# ============================================================
# GET CUSTOMER KHATA HISTORY API
# Purpose: Retrieve all credit and repayment transactions.
# Method: GET
# Endpoint: /customers/{customer_id}/khata/transactions
# ============================================================

@app.get(
    "/customers/{customer_id}/khata/transactions",
    response_model=list[KhataTransactionResponse]
)
def get_customer_khata_history(
    customer_id: int,
    db: Session = Depends(get_db)
):
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        transactions = (
            db.query(KhataTransaction)
            .filter(
                KhataTransaction.customer_id == customer_id
            )
            .order_by(KhataTransaction.created_at.desc())
            .all()
        )

        return transactions

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve Khata history"
        )

    # ============================================================
# GET ALL CUSTOMER OUTSTANDING DUES API
# Purpose: Show customers who have pending Khata balances.
# Method: GET
# Endpoint: /khata/outstanding
# ============================================================

@app.get("/khata/outstanding")
def get_all_customer_outstanding(db: Session = Depends(get_db)):
    try:
        results = (
            db.query(
                Customer.id.label("customer_id"),
                Customer.name.label("customer_name"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                KhataTransaction.transaction_type == "credit",
                                KhataTransaction.amount
                            ),
                            else_=0
                        )
                    ), 0
                ).label("total_credit"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                KhataTransaction.transaction_type == "repayment",
                                KhataTransaction.amount
                            ),
                            else_=0
                        )
                    ), 0
                ).label("total_repayments")
            )
            .join(
                KhataTransaction,
                Customer.id == KhataTransaction.customer_id
            )
            .group_by(Customer.id, Customer.name)
            .all()
        )

        outstanding_customers = []

        for row in results:
            balance = row.total_credit - row.total_repayments

            if balance > 0:
                outstanding_customers.append({
                    "customer_id": row.customer_id,
                    "customer_name": row.customer_name,
                    "total_credit": row.total_credit,
                    "total_repayments": row.total_repayments,
                    "outstanding_balance": balance
                })

        return {
            "total_customers_with_dues": len(outstanding_customers),
            "total_outstanding_amount": sum(
                item["outstanding_balance"]
                for item in outstanding_customers
            ),
            "customers": outstanding_customers
        }

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve outstanding customer dues"
        )


    
# ============================================================
# SUPPLIER DUES SUMMARY API
# Purpose: Calculate total purchases, payments and outstanding
#          dues for each supplier.
# Method: GET
# Endpoint: /suppliers/dues/summary
# ============================================================

@app.get("/suppliers/dues/summary")
def get_supplier_dues_summary(
    db: Session = Depends(get_db)
):
    try:
        # Calculate total payments made for each purchase
        payment_totals = (
            db.query(
                PurchasePayment.purchase_id.label("purchase_id"),
                func.sum(PurchasePayment.amount).label("total_paid")
            )
            .group_by(PurchasePayment.purchase_id)
            .subquery()
        )

        # Calculate supplier-wise purchase and payment totals
        results = (
            db.query(
                Supplier.id.label("supplier_id"),
                Supplier.name.label("supplier_name"),

                func.coalesce(
                    func.sum(Purchase.total_amount), 0
                ).label("total_purchases"),

                func.coalesce(
                    func.sum(payment_totals.c.total_paid), 0
                ).label("total_paid")
            )
            .join(
                Purchase,
                Purchase.supplier_id == Supplier.id
            )
            .outerjoin(
                payment_totals,
                payment_totals.c.purchase_id == Purchase.id
            )
            .group_by(Supplier.id, Supplier.name)
            .all()
        )

        suppliers_with_dues = []

        for row in results:
            outstanding = row.total_purchases - row.total_paid

            if outstanding > 0:
                suppliers_with_dues.append({
                    "supplier_id": row.supplier_id,
                    "supplier_name": row.supplier_name,
                    "total_purchases": row.total_purchases,
                    "total_paid": row.total_paid,
                    "outstanding_balance": outstanding
                })

        total_outstanding = sum(
            item["outstanding_balance"]
            for item in suppliers_with_dues
        )

        return {
            "total_suppliers_with_dues": len(suppliers_with_dues),
            "total_outstanding_amount": total_outstanding,
            "suppliers": suppliers_with_dues
        }

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve supplier dues summary"
        )

# ============================================================
# GET INDIVIDUAL SUPPLIER DUES API
# Purpose: Calculate purchase, payment and outstanding balance
#          for one specific supplier.
# Method: GET
# Endpoint: /suppliers/{supplier_id}/dues
# ============================================================

@app.get("/suppliers/{supplier_id}/dues")
def get_supplier_dues(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        total_purchases = (
            db.query(
                func.coalesce(func.sum(Purchase.total_amount), 0)
            )
            .filter(Purchase.supplier_id == supplier_id)
            .scalar()
        )

        total_paid = (
            db.query(
                func.coalesce(func.sum(PurchasePayment.amount), 0)
            )
            .join(
                Purchase,
                Purchase.id == PurchasePayment.purchase_id
            )
            .filter(Purchase.supplier_id == supplier_id)
            .scalar()
        )

        outstanding = total_purchases - total_paid

        return {
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "total_purchases": total_purchases,
            "total_paid": total_paid,
            "outstanding_balance": outstanding
        }

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve supplier dues"
        )


    # ============================================================
# SUPPLIER PAYMENT HISTORY API
# Purpose: Retrieve all payments made against a supplier's
#          purchase invoices.
# Method: GET
# Endpoint: /suppliers/{supplier_id}/payments
# ============================================================

@app.get("/suppliers/{supplier_id}/payments")
def get_supplier_payment_history(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    try:
        supplier = db.query(Supplier).filter(
            Supplier.id == supplier_id
        ).first()

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

        payments = (
            db.query(PurchasePayment, Purchase)
            .join(
                Purchase,
                Purchase.id == PurchasePayment.purchase_id
            )
            .filter(Purchase.supplier_id == supplier_id)
            .order_by(PurchasePayment.paid_at.desc())
            .all()
        )

        payment_history = []

        for payment, purchase in payments:
            payment_history.append({
                "payment_id": payment.id,
                "purchase_id": purchase.id,
                "invoice_number": purchase.invoice_number,
                "amount": payment.amount,
                "payment_method": payment.payment_method,
                "transaction_reference": payment.transaction_reference,
                "notes": payment.notes,
                "paid_at": payment.paid_at
            })

        return {
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "total_payments": len(payment_history),
            "payments": payment_history
        }

    except HTTPException:
        raise

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve supplier payment history"
        )

    

# ============================================================
# OVERALL FINANCIAL SUMMARY API
# Purpose: Summarize customer outstanding dues and supplier
#          outstanding payments.
# Method: GET
# Endpoint: /finance/summary
# ============================================================

@app.get("/finance/summary")
def get_financial_summary(
    db: Session = Depends(get_db)
):
    try:
        # Calculate total customer credit
        total_customer_credit = (
            db.query(
                func.coalesce(func.sum(KhataTransaction.amount), 0)
            )
            .filter(
                KhataTransaction.transaction_type == "credit"
            )
            .scalar()
        )

        # Calculate total customer repayments
        total_customer_repayments = (
            db.query(
                func.coalesce(func.sum(KhataTransaction.amount), 0)
            )
            .filter(
                KhataTransaction.transaction_type == "repayment"
            )
            .scalar()
        )

        # Convert customer amounts to Decimal
        total_customer_credit = Decimal(str(total_customer_credit))
        total_customer_repayments = Decimal(str(total_customer_repayments))

        customer_outstanding = (
            total_customer_credit - total_customer_repayments
        )

        # Calculate total supplier purchases
        total_supplier_purchases = (
            db.query(
                func.coalesce(func.sum(Purchase.total_amount), 0)
            )
            .scalar()
        )

        # Calculate total supplier payments
        total_supplier_payments = (
            db.query(
                func.coalesce(func.sum(PurchasePayment.amount), 0)
            )
            .scalar()
        )

        # Convert supplier amounts to Decimal
        total_supplier_purchases = Decimal(str(total_supplier_purchases))
        total_supplier_payments = Decimal(str(total_supplier_payments))

        supplier_outstanding = (
            total_supplier_purchases - total_supplier_payments
        )

        # Calculate net receivables/payables position
        net_position = (
            customer_outstanding - supplier_outstanding
        )

        return {
            "customer_finances": {
                "total_credit": total_customer_credit,
                "total_repayments": total_customer_repayments,
                "outstanding_receivables": customer_outstanding
            },
            "supplier_finances": {
                "total_purchases": total_supplier_purchases,
                "total_payments": total_supplier_payments,
                "outstanding_payables": supplier_outstanding
            },
            "net_receivables_payables_position": net_position
        }

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to generate financial summary"
        )
