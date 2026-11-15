from fastapi import FastAPI, Depends, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.batch_verification import BatchVerification
from app.models.supplier import Supplier
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_payment import PurchasePayment
from app.models.customer import Customer
from app.models.khata_transaction import KhataTransaction
from app.models.sale import Sale
from app.models.sale_item import SaleItem

from app.database import Base, engine, get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.product_batch import ProductBatch
from app.models.expiry_record import ExpiryRecord
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.models.purchase_proposal import PurchaseProposal
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


# Sales transaction schemas
from app.schemas.sale import (
    SaleCreate,
    SaleResponse,
    SaleItemCreate,
    SaleItemResponse
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



# ==========================================
# AUTHENTICATION ROUTER
# Purpose: Register authentication endpoints.
# ==========================================

from app.auth.routes import router as auth_router, require_shop_staff, get_current_user

app.include_router(auth_router)

# Owner-controlled cash budgets and purchase proposal approval.
# This router records approval only; it never places supplier orders.
from app.routers.purchase_planning import router as purchase_planning_router
app.include_router(purchase_planning_router)

from app.routers.agent_workflows import router as agent_workflows_router
app.include_router(agent_workflows_router)

from app.routers.shop_operations import router as shop_operations_router
app.include_router(shop_operations_router)





# ---------------------------------------------------------
# MIDDLEWARE: Cross-Origin Resource Sharing
# Purpose: Allow the Flutter Web application to communicate
# with the FastAPI backend during local development.
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Legacy endpoints that expose cross-shop data are intentionally disabled.
# Phase 1 uses the tenant-scoped /shops/{shop_id}/... APIs instead.
@app.middleware("http")
async def block_unscoped_legacy_endpoints(request: Request, call_next):
    path = request.url.path
    blocked = (
        path == "/stock-movements"
        or path.startswith("/inventory/saleable-stock/")
        or path == "/inventory/reconcile-batches"
        or path.startswith("/expiry-records")
        or path == "/suppliers"
        or path.startswith("/suppliers/")
        or path == "/customers"
        or path.startswith("/customers/")
        or path.startswith("/khata")
        or path == "/finance/summary"
        or path.startswith("/analytics/sales/")
        or path in {"/agents/sales/chat", "/agents/inventory/chat"}
        or path == "/test/create-expired-batch"
        or path.startswith("/purchases/")
        or (
            path.startswith("/inventory/")
            and path not in {"/inventory/summary", "/inventory/restock-recommendations"}
        )
    )
    if blocked:
        return JSONResponse(
            status_code=410,
            content={
                "detail": "This legacy endpoint is disabled because it is not tenant-scoped. Use the authenticated shop-specific API.",
            },
        )
    return await call_next(request)


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
def get_products(
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return db.query(Product).filter(
        Product.shop_id == shop_id, Product.is_active.is_(True)
    ).all()





# POST: Add a new product
@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    product_data: ProductCreate,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    if float(product_data.quantity or 0) != 0:
        raise HTTPException(
            status_code=400,
            detail="Create the product with zero stock, then record opening stock with a batch and expiry date.",
        )
    product = Product(**product_data.model_dump(), shop_id=shop_id)

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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.shop_id == shop_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = product_data.model_dump(exclude_unset=True)
    if "quantity" in update_data:
        raise HTTPException(
            status_code=400,
            detail="Use the audited inventory adjustment endpoint to change stock quantities.",
        )

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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.shop_id == shop_id,
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return {
        "message": "Product deleted successfully!"
    }


# GET: View all low-stock products
@app.get("/products/low-stock", response_model=list[ProductResponse])
def get_low_stock_products(
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    return db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
        Product.quantity <= Product.minimum_stock,
    ).all()

# GET: View stock status of all products
@app.get("/products/stock-status")
def get_stock_status(
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
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
def get_product(
    product_id: int,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.shop_id == shop_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product



# GET: Inventory Summary Dashboard
@app.get("/inventory/summary")
def get_inventory_summary(
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    products = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.is_active.is_(True),
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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
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
        performed_by = current_user.id
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
            Product.shop_id == shop_id,
            Product.is_active.is_(True),
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
# Create expiry action requests for disposal
# or supplier return without deducting stock.
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

        # Validate supplier information
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

        # Calculate outstanding action reservations.
        # Include pending owner approvals and approved
        # actions that have not yet been completed.
        open_requests = db.query(ExpiryRecord).filter(
            ExpiryRecord.batch_id == batch.id,
            ExpiryRecord.action == action,
            ExpiryRecord.action_status.in_(
                ["requested", "approved"]
            )
        ).all()

        reserved_quantity = sum(
            record.quantity for record in open_requests
        )

        # Prevent overlapping disposal and return requests
        # against the same physical batch.
        all_open_requests = db.query(ExpiryRecord).filter(
            ExpiryRecord.batch_id == batch.id,
            ExpiryRecord.action_status.in_(
                ["requested", "approved"]
            )
        ).all()

        total_reserved = sum(
            record.quantity for record in all_open_requests
        )

        available_quantity = batch.quantity - total_reserved

        if quantity > available_quantity:
            raise HTTPException(
                400,
                "Quantity exceeds available stock after existing expiry action reservations"
            )

        if quantity > product.quantity:
            raise HTTPException(
                400,
                "Quantity exceeds main inventory stock"
            )

        # Create request only.
        # No stock deduction happens at this stage.
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
            ),
            approval_status="pending",
            action_status="requested"
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "message": "Expiry action request created. Waiting for owner approval.",
            "record_id": record.id,
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "action": action,
            "quantity": quantity,
            "approval_status": record.approval_status,
            "action_status": record.action_status,
            "return_status": record.return_status,
            "supplier_id": record.supplier_id,
            "supplier_name": record.supplier_name,
            "previous_stock": product.quantity,
            "current_stock": product.quantity,
            "remaining_batch_quantity": batch.quantity,
            "reserved_quantity": total_reserved + quantity,
            "inventory_deducted": False
        }

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
# SUPPLIER RESPONSE API
# Purpose:
# Allow a supplier to accept or reject an
# owner-approved supplier return request.
#
# Owner approval is mandatory before the
# supplier can respond.
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

        # Validate record ID
        if (
            not isinstance(record_id, int)
            or isinstance(record_id, bool)
            or record_id <= 0
        ):
            raise HTTPException(400, "Invalid record ID")

        # Validate supplier response status
        if status not in ["accepted", "rejected"]:
            raise HTTPException(
                400,
                "Status must be accepted or rejected"
            )

        # Validate supplier reference
        if supplier_reference is not None and (
            not isinstance(supplier_reference, str)
            or len(supplier_reference) > 100
        ):
            raise HTTPException(
                400,
                "Invalid supplier reference"
            )

        # Find initial record reference
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(404, "Expiry record not found")

        # Find batch reference
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

        # Lock batch second
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == record_reference.batch_id,
            ProductBatch.product_id == product.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(404, "Batch not found")

        # Lock expiry record last
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        if not record:
            raise HTTPException(404, "Expiry record not found")

        # Only supplier return requests are allowed
        if record.action != "supplier_return":
            raise HTTPException(
                400,
                "This record is not a supplier return request"
            )

        # Owner approval is mandatory
        if record.approval_status != "approved":
            raise HTTPException(
                403,
                "Owner approval is required before supplier response"
            )

        # Request must still be active
        if record.action_status != "requested":
            raise HTTPException(
                400,
                "This supplier return request is not active"
            )

        # Only pending supplier responses can be updated
        if record.return_status != "pending":
            raise HTTPException(
                400,
                "Only pending supplier requests can be updated"
            )

        # Find registered supplier
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

        # Update supplier response
        record.return_status = status

        if supplier_reference is not None:
            record.supplier_reference = supplier_reference.strip()

        # Preserve existing supplier acceptance timestamp behavior
        if status == "accepted":
            record.approved_at = datetime.now(timezone.utc)

        # Rejected requests no longer reserve stock
        if status == "rejected":
            record.action_status = "cancelled"

        db.commit()

        db.refresh(record)
        db.refresh(product)
        db.refresh(batch)

        return {
            "message": (
                "Supplier return accepted successfully"
                if status == "accepted"
                else "Supplier return rejected successfully"
            ),
            "record_id": record.id,
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "approval_status": record.approval_status,
            "supplier_response": record.return_status,
            "action_status": record.action_status,
            "supplier_reference": record.supplier_reference,
            "owner_approved_at": record.owner_approved_at,
            "supplier_accepted_at": record.approved_at,
            "inventory_deducted": False
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Supplier response error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to process supplier response"
        )


# ==========================================
# SUPPLIER PICKUP CONFIRMATION API
# Purpose:
# 1. Confirm physical pickup of returned goods.
# 2. Require owner approval and supplier acceptance.
# 3. Deduct inventory exactly once.
# 4. Record stock movement for audit history.
# 5. Mark the expiry action as completed.
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

        # Validate record ID
        if (
            not isinstance(record_id, int)
            or isinstance(record_id, bool)
            or record_id <= 0
        ):
            raise HTTPException(400, "Invalid record ID")

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

        # Find return record reference
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(404, "Expiry record not found")

        if record_reference.action != "supplier_return":
            raise HTTPException(
                400,
                "Not a supplier return record"
            )

        # Find batch reference
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

        # Lock batch second
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == record_reference.batch_id,
            ProductBatch.product_id == product.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(404, "Batch not found")

        # Lock expiry record last
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        if not record:
            raise HTTPException(404, "Expiry record not found")

        # Owner approval is mandatory
        if record.approval_status != "approved":
            raise HTTPException(
                403,
                "Owner approval is required before supplier pickup"
            )

        # Supplier must have accepted the return
        if record.return_status != "accepted":
            raise HTTPException(
                409,
                "Only accepted supplier return requests can be picked up"
            )

        # Prevent duplicate pickup
        if record.action_status == "completed":
            raise HTTPException(
                409,
                "Supplier pickup has already been completed"
            )

        if record.action_status != "requested":
            raise HTTPException(
                400,
                "This supplier return request cannot be processed"
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
        quantity = float(record.quantity)

        if not math.isfinite(quantity) or quantity <= 0:
            raise HTTPException(
                400,
                "Invalid return quantity"
            )

        if quantity > batch.quantity:
            raise HTTPException(
                409,
                "Insufficient batch stock for pickup"
            )

        if quantity > product.quantity:
            raise HTTPException(
                409,
                "Insufficient product stock for pickup"
            )

        # Capture previous stock
        previous_stock = product.quantity
        previous_batch_quantity = batch.quantity

        # Deduct inventory exactly once
        batch.quantity -= quantity
        product.quantity -= quantity

        # Update supplier return status
        record.return_status = "picked_up"
        record.picked_up_at = datetime.now(timezone.utc)

        # Mark action as completed
        record.action_status = "completed"
        record.action_completed_at = datetime.now(timezone.utc)

        # Create stock movement for audit history
        movement = StockMovement(
            product_id=product.id,
            movement_type="supplier_return",
            quantity_change=-quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason=f"Supplier pickup: {supplier.name}",
            performed_by=performed_by,
            reference_type="expiry_record",
            reference_id=record.id
        )

        db.add(movement)

        db.commit()

        db.refresh(record)
        db.refresh(product)
        db.refresh(batch)
        db.refresh(movement)

        return {
            "message": "Supplier pickup confirmed successfully",
            "record_id": record.id,
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "approval_status": record.approval_status,
            "return_status": record.return_status,
            "action_status": record.action_status,
            "quantity_returned": quantity,
            "previous_product_stock": previous_stock,
            "remaining_product_stock": product.quantity,
            "previous_batch_quantity": previous_batch_quantity,
            "remaining_batch_quantity": batch.quantity,
            "movement_id": movement.id,
            "picked_up_at": record.picked_up_at,
            "action_completed_at": record.action_completed_at
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


# ==========================================
# SUPPLIER CREDIT CONFIRMATION API
# Purpose:
# 1. Record supplier credit after pickup.
# 2. Require owner approval.
# 3. Verify physical pickup is completed.
# 4. Prevent duplicate credit recording.
# 5. Maintain supplier credit audit details.
#
# Method: PUT
# Endpoint: /expiry-records/{record_id}/credit
# ==========================================

@app.put("/expiry-records/{record_id}/credit")
def confirm_supplier_credit(
    record_id: int,
    credit_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        credit_amount = credit_data.get("credit_amount")

        # Validate record ID
        if (
            not isinstance(record_id, int)
            or isinstance(record_id, bool)
            or record_id <= 0
        ):
            raise HTTPException(400, "Invalid record ID")

        # Validate credit amount
        try:
            credit_amount = float(credit_amount)
        except (ValueError, TypeError):
            raise HTTPException(
                400,
                "Invalid credit amount"
            )

        if (
            not math.isfinite(credit_amount)
            or credit_amount <= 0
        ):
            raise HTTPException(
                400,
                "Credit amount must be greater than zero"
            )

        # Lock the return record
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        if not record:
            raise HTTPException(
                404,
                "Return record not found"
            )

        # Validate action type
        if record.action != "supplier_return":
            raise HTTPException(
                400,
                "This is not a supplier return"
            )

        # Owner approval is mandatory
        if record.approval_status != "approved":
            raise HTTPException(
                403,
                "Owner approval is required before recording supplier credit"
            )

        # Physical pickup must be completed
        if record.return_status != "picked_up":
            raise HTTPException(
                409,
                "Supplier pickup must be confirmed before recording credit"
            )

        # Action must be completed
        if record.action_status != "completed":
            raise HTTPException(
                409,
                "Supplier pickup action must be completed before recording credit"
            )

        # Prevent duplicate credit recording
        if (
            record.credit_amount is not None
            or record.credited_at is not None
            or record.return_status == "credited"
        ):
            raise HTTPException(
                409,
                "Supplier credit has already been recorded"
            )

        # Fetch registered supplier details
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

        # Record supplier-reported credit
        record.credit_amount = credit_amount
        record.credited_at = datetime.now(timezone.utc)
        record.return_status = "credited"

        db.commit()
        db.refresh(record)

        return {
            "message": "Supplier credit recorded successfully",
            "record_id": record.id,
            "supplier_id": record.supplier_id,
            "supplier_name": supplier.name,
            "approval_status": record.approval_status,
            "action_status": record.action_status,
            "quantity_returned": record.quantity,
            "credit_amount": record.credit_amount,
            "return_status": record.return_status,
            "credited_at": record.credited_at,
            "credit_verified": False
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

# ============================================================
# OWNER APPROVAL API
# Purpose: Allow the shop owner to approve or reject
#          expiry disposal and supplier return requests.
# Method: PUT
# Endpoint: /expiry-records/{record_id}/approval
# ============================================================

@app.put("/expiry-records/{record_id}/approval")
def approve_expiry_action(
    record_id: int,
    approval_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    try:
        # Read approval information
        status = approval_data.get("status")
        approved_by = approval_data.get("approved_by")

        # Validate approval status
        if status not in ["approved", "rejected"]:
            raise HTTPException(
                status_code=400,
                detail="Status must be approved or rejected"
            )

        # Validate owner ID
        if (
            not isinstance(approved_by, int)
            or isinstance(approved_by, bool)
            or approved_by <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="A valid approved_by value is required"
            )

        # Lock the expiry record
        record = (
            db.query(ExpiryRecord)
            .filter(ExpiryRecord.id == record_id)
            .with_for_update()
            .first()
        )

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Expiry record not found"
            )

        # Check supported action
        if record.action not in ["disposal", "supplier_return"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid expiry action"
            )

        # Only pending requests can be reviewed
        if record.approval_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Request is already "
                    f"{record.approval_status}"
                )
            )

        # Update owner approval
        record.approval_status = status

        if status == "approved":
            record.approved_by = approved_by
            record.owner_approved_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(record)

        return {
            "message": f"Expiry action {status} successfully",
            "record_id": record.id,
            "action": record.action,
            "approval_status": record.approval_status,
            "approved_by": record.approved_by,
            "owner_approved_at": record.owner_approved_at
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Unable to process owner approval"
        )



   

import math

# ---------------------------------------------------------
# API: Multi-Product FEFO Sales Management
# Method: POST
# Endpoint: /sales
# Purpose:
# Processes a customer bill containing multiple products.
# Deducts verified, unexpired batches using FEFO.
# Stores historical selling prices and links each sale item
# to its corresponding stock movement.
# All changes are committed as one database transaction.
# ---------------------------------------------------------

@app.post("/sales", response_model=SaleResponse)
def create_sale(
    sale_data: SaleCreate,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    try:
        today = date.today()
        tolerance = 0.000001

        # Validate duplicate product entries
        product_ids = [
            item.product_id for item in sale_data.items
        ]

        if len(product_ids) != len(set(product_ids)):
            raise HTTPException(
                status_code=400,
                detail="A product can appear only once in a bill."
            )

        # Lock active products in a consistent order
        products = db.query(Product).filter(
            Product.id.in_(product_ids),
            Product.shop_id == shop_id,
            Product.is_active.is_(True)
        ).order_by(
            Product.id.asc()
        ).with_for_update().all()

        product_map = {
            product.id: product for product in products
        }

        if len(product_map) != len(product_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more products were not found or are inactive."
            )

        # Prepare and validate all sale items before changing stock
        sale_plans = []
        items_subtotal = 0.0
        total_item_discount = 0.0

        for item in sale_data.items:

            quantity = float(item.quantity)
            item_discount = float(item.discount_amount)

            if not math.isfinite(quantity) or quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid quantity for product {item.product_id}."
                )

            if not math.isfinite(item_discount) or item_discount < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid discount for product {item.product_id}."
                )

            product = product_map[item.product_id]

            unit_price = float(product.selling_price)

            if not math.isfinite(unit_price) or unit_price < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid selling price for {product.name}."
                )

            gross_amount = quantity * unit_price

            if item_discount > gross_amount + tolerance:
                raise HTTPException(
                    status_code=400,
                    detail=f"Discount exceeds product amount for {product.name}."
                )

            line_subtotal = gross_amount - item_discount

            # Lock positive-stock batches in FEFO order
            batches = db.query(ProductBatch).filter(
                ProductBatch.product_id == product.id,
                ProductBatch.quantity > 0
            ).order_by(
                ProductBatch.expiry_date.asc(),
                ProductBatch.id.asc()
            ).with_for_update().all()

            total_batch_stock = sum(
                float(batch.quantity) for batch in batches
            )

            # Check main inventory and batch consistency
            if abs(total_batch_stock - float(product.quantity)) > tolerance:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Batch stock mismatch for {product.name}. "
                        "Reconcile inventory before processing this bill."
                    )
                )

            # Only verified and unexpired stock is saleable
            eligible_batches = [
                batch for batch in batches
                if batch.is_verified and batch.expiry_date >= today
            ]

            available_stock = sum(
                float(batch.quantity) for batch in eligible_batches
            )

            if quantity > available_stock + tolerance:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient verified, unexpired stock for "
                        f"{product.name}. Available: {available_stock}"
                    )
                )

            sale_plans.append({
                "product": product,
                "batches": eligible_batches,
                "quantity": quantity,
                "unit_price": unit_price,
                "item_discount": item_discount,
                "line_subtotal": line_subtotal
            })

            items_subtotal += line_subtotal
            total_item_discount += item_discount

        # Validate bill-level discount
        bill_discount = float(sale_data.discount_amount)

        if not math.isfinite(bill_discount) or bill_discount < 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid bill discount."
            )

        if bill_discount > items_subtotal + tolerance:
            raise HTTPException(
                status_code=400,
                detail="Bill discount cannot exceed the bill subtotal."
            )

        final_total = max(0.0, items_subtotal - bill_discount)

        total_discount = total_item_discount + bill_discount

        # Create the main sales transaction
        sale = Sale(
            shop_id=shop_id,
            total_amount=final_total,
            discount_amount=total_discount,
            payment_method=sale_data.payment_method.value,
            notes=sale_data.notes
        )

        db.add(sale)
        db.flush()

        response_items = []

        # Process every product using FEFO
        for plan in sale_plans:

            product = plan["product"]
            quantity = plan["quantity"]
            remaining = quantity

            quantity_before = float(product.quantity)

            batch_updates = []

            for batch in plan["batches"]:

                if remaining <= tolerance:
                    break

                batch_available = float(batch.quantity)

                sold = min(batch_available, remaining)

                batch.quantity = max(0.0, batch_available - sold)

                remaining -= sold

                batch_updates.append({
                    "batch_id": batch.id,
                    "quantity_sold": sold
                })

            if remaining > tolerance:
                raise HTTPException(
                    status_code=409,
                    detail=f"FEFO deduction failed for {product.name}."
                )

            # Update main inventory
            product.quantity = max(
                0.0,
                quantity_before - quantity
            )

            # Create stock movement for this product
            movement = StockMovement(
                product_id=product.id,
                movement_type="sale",
                quantity_change=-quantity,
                quantity_before=quantity_before,
                quantity_after=product.quantity,
                reason="FEFO sale from verified batches",
                reference_type="sale",
                reference_id=sale.id
            )

            db.add(movement)
            db.flush()

            # Store historical sale item details
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                stock_movement_id=movement.id,
                product_name=product.name,
                unit=product.unit,
                quantity=quantity,
                unit_price=plan["unit_price"],
                discount_amount=plan["item_discount"],
                subtotal=plan["line_subtotal"]
            )

            db.add(sale_item)

            response_items.append({
                "id": None,
                "product_id": product.id,
                "stock_movement_id": movement.id,
                "product_name": product.name,
                "unit": product.unit,
                "quantity": quantity,
                "unit_price": plan["unit_price"],
                "discount_amount": plan["item_discount"],
                "subtotal": plan["line_subtotal"],
                "quantity_before": quantity_before,
                "remaining_stock": product.quantity,
                "batch_updates": batch_updates
            })

        # Commit the entire bill atomically
        db.commit()
                # ---------------------------------------------
        # Invalidate sales analytics cache after commit
        # ---------------------------------------------

        try:
            from app.services.sales_analytics_cache import (
                invalidate_sales_analytics_cache
            )

            invalidate_sales_analytics_cache()

        except Exception as cache_error:
            print(
                "Sales cache invalidation error:",
                str(cache_error)
            )
        db.refresh(sale)

        # Build transaction response
        saved_items = db.query(SaleItem).filter(
            SaleItem.sale_id == sale.id
        ).all()

        return {
            "id": sale.id,
            "total_amount": sale.total_amount,
            "discount_amount": sale.discount_amount,
            "payment_method": sale.payment_method,
            "notes": sale.notes,
            "created_at": sale.created_at,
            "items": saved_items
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to process sales transaction."
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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
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

        performed_by = current_user.id
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
        batch_reference = db.query(ProductBatch).join(
            Product, Product.id == ProductBatch.product_id
        ).filter(
            ProductBatch.id == batch_id,
            Product.shop_id == shop_id,
        ).first()

        if not batch_reference:
            raise HTTPException(
                status_code=404,
                detail="Batch not found"
            )

        # Lock product first
        product = db.query(Product).filter(
            Product.id == batch_reference.product_id,
            Product.shop_id == shop_id,
            Product.is_active.is_(True)
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
    shop_id: int = Query(..., gt=0),
    batch_id: int = None,
    performed_by: int = None,
    limit: int = 50,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
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
        ).filter(Product.shop_id == shop_id)

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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    try:
        if batch_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid batch ID"
            )

        # Check whether batch exists
        batch = db.query(ProductBatch).join(
            Product, Product.id == ProductBatch.product_id
        ).filter(
            ProductBatch.id == batch_id,
            Product.shop_id == shop_id,
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
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    current_user=Depends(get_current_user),
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
        connection = db.query(ShopDistributorConnection).filter(
            ShopDistributorConnection.shop_id == shop_id,
            ShopDistributorConnection.supplier_id == supplier.id,
            ShopDistributorConnection.is_active.is_(True),
        ).first()
        if connection is None:
            raise HTTPException(409, "Supplier is not connected to this shop")

        # 2. Validate purchase items
        total_amount = 0
        validated_items = []

        for item in purchase_data.items:

            product = db.query(Product).filter(
                Product.id == item.product_id,
                Product.shop_id == shop_id,
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
            shop_id=shop_id,
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
                performed_by=current_user.id,
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



# ============================================================
# FAST-MOVING PRODUCTS API
# Purpose: Identify products with the highest sales quantities.
# Method: GET
# Endpoint: /inventory/fast-moving
# Default period: Last 30 days
# ============================================================

@app.get("/inventory/fast-moving")
def get_fast_moving_products(
    days: int = 30,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        # Validate input parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 100"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate total quantity sold per product
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.unit.label("unit"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold"),
                func.count(
                    StockMovement.id
                ).label("number_of_sales")
            )
            .join(
                StockMovement,
                StockMovement.product_id == Product.id
            )
            .join(Product, Product.id == StockMovement.product_id)
            .filter(
                Product.shop_id == shop_id,
                StockMovement.movement_type == "sale",
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(
                Product.id,
                Product.name,
                Product.unit
            )
            .order_by(
                func.sum(
                    -StockMovement.quantity_change
                ).desc()
            )
            .limit(limit)
            .all()
        )

        fast_moving_products = []

        for rank, row in enumerate(results, start=1):
            fast_moving_products.append({
                "rank": rank,
                "product_id": row.product_id,
                "product_name": row.product_name,
                "unit": row.unit,
                "total_quantity_sold": row.total_quantity_sold,
                "number_of_sales": row.number_of_sales
            })

        return {
            "period_days": days,
            "total_products": len(fast_moving_products),
            "fast_moving_products": fast_moving_products
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve fast-moving products"
        )




# ============================================================
# SLOW-MOVING PRODUCTS API
# Purpose: Identify products with low sales activity.
# Method: GET
# Endpoint: /inventory/slow-moving
# Default period: Last 30 days
# ============================================================

@app.get("/inventory/slow-moving")
def get_slow_moving_products(
    days: int = 30,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        # Validate parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 100"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate sales quantity for each product
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold"),
                func.count(
                    StockMovement.id
                ).label("number_of_sales")
            )
            .join(Product, Product.id == StockMovement.product_id)
            .filter(
                Product.shop_id == shop_id,
                StockMovement.movement_type == "sale",
                StockMovement.quantity_change < 0,
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Include products with no sales as zero sales
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.unit.label("unit"),
                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ).label("total_quantity_sold"),
                func.coalesce(
                    sales_subquery.c.number_of_sales, 0
                ).label("number_of_sales")
            )
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(Product.is_active == True)
            .order_by(
                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ).asc(),
                Product.name.asc()
            )
            .limit(limit)
            .all()
        )

        slow_moving_products = []

        for row in results:
            slow_moving_products.append({
                "product_id": row.product_id,
                "product_name": row.product_name,
                "unit": row.unit,
                "total_quantity_sold": row.total_quantity_sold,
                "number_of_sales": row.number_of_sales
            })

        return {
            "period_days": days,
            "total_products": len(slow_moving_products),
            "slow_moving_products": slow_moving_products
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve slow-moving products"
        )



# ============================================================
# DEAD STOCK DETECTION API
# Purpose: Identify active products with available stock but
#          no recorded sales during the selected period.
# Method: GET
# Endpoint: /inventory/dead-stock
# Default period: Last 90 days
# ============================================================

@app.get("/inventory/dead-stock")
def get_dead_stock(
    days: int = 90,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    try:
        # Validate parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if limit < 1 or limit > 500:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 500"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate sales during the selected period
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold"),
                func.count(
                    StockMovement.id
                ).label("number_of_sales")
            )
            .filter(
                StockMovement.movement_type == "sale",
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Find active products with stock but no sales
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.quantity.label("current_stock"),
                Product.unit.label("unit")
            )
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(
                Product.is_active == True,
                Product.quantity > 0,
                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ) == 0
            )
            .order_by(Product.quantity.desc())
            .limit(limit)
            .all()
        )

        dead_stock_products = []

        for row in results:
            dead_stock_products.append({
                "product_id": row.product_id,
                "product_name": row.product_name,
                "current_stock": row.current_stock,
                "unit": row.unit,
                "days_without_sales": days
            })

        return {
            "analysis_period_days": days,
            "total_dead_stock_products": len(dead_stock_products),
            "dead_stock_products": dead_stock_products
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to detect dead stock"
        )




# ============================================================
# SMART RESTOCK RECOMMENDATIONS API
# Purpose: Identify products requiring restocking based on
#          minimum stock and estimated stock coverage.
# Method: GET
# Endpoint: /inventory/restock-recommendations
# Analysis period: Last 30 days
# Warning threshold: 7 days of stock remaining
# ============================================================

@app.get("/inventory/restock-recommendations")
def get_restock_recommendations(
    shop_id: int = Query(..., gt=0),
    days: int = 30,
    warning_days: int = 7,
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db),
):
    try:
        # Validate parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if warning_days < 1 or warning_days > 90:
            raise HTTPException(
                status_code=400,
                detail="Warning days must be between 1 and 90"
            )

        # Calculate analysis period
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate product-wise sales
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold")
            )
            .filter(
                StockMovement.movement_type == "sale",
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Retrieve active products
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.quantity.label("current_stock"),
                Product.minimum_stock.label("minimum_stock"),
                Product.unit.label("unit"),
                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ).label("total_quantity_sold")
            )
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(
                Product.shop_id == shop_id,
                Product.is_active.is_(True),
            )
            .all()
        )

        recommendations = []

        for row in results:
            current_stock = float(row.current_stock or 0)
            minimum_stock = float(row.minimum_stock or 0)
            total_sold = float(row.total_quantity_sold or 0)

            # Calculate average daily sales
            average_daily_sales = total_sold / days

            # Estimate remaining stock days
            if average_daily_sales > 0:
                estimated_days_remaining = (
                    current_stock / average_daily_sales
                )
            else:
                estimated_days_remaining = None

            # Check minimum stock condition
            minimum_stock_warning = (
                current_stock <= minimum_stock
            )

            # Check 7-day stock coverage condition
            low_coverage_warning = (
                estimated_days_remaining is not None
                and estimated_days_remaining <= warning_days
            )

            # Recommend only products meeting either condition
            if not minimum_stock_warning and not low_coverage_warning:
                continue

            # Calculate target stock for 30 days of demand
            target_stock = max(
                minimum_stock * 2,
                average_daily_sales * 30
            )

            # Calculate suggested reorder quantity
            suggested_reorder_quantity = max(
                0,
                target_stock - current_stock
            )

            recommendations.append({
                "product_id": row.product_id,
                "product_name": row.product_name,
                "current_stock": current_stock,
                "minimum_stock": minimum_stock,
                "unit": row.unit,
                "total_quantity_sold": total_sold,
                "average_daily_sales": round(
                    average_daily_sales, 2
                ),
                "estimated_days_remaining": (
                    round(estimated_days_remaining, 2)
                    if estimated_days_remaining is not None
                    else None
                ),
                "minimum_stock_warning": minimum_stock_warning,
                "low_coverage_warning": low_coverage_warning,
                "target_stock": round(target_stock, 2),
                "suggested_reorder_quantity": round(
                    suggested_reorder_quantity, 2
                )
            })

        # Prioritize products with the least stock coverage
        recommendations.sort(
            key=lambda item: (
                item["estimated_days_remaining"]
                if item["estimated_days_remaining"] is not None
                else float("inf")
            )
        )

        return {
            "analysis_period_days": days,
            "warning_threshold_days": warning_days,
            "total_products_requiring_restock": len(recommendations),
            "recommendations": recommendations
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to generate restock recommendations"
        )




# ============================================================
# STOCK COVERAGE REPORT API
# Purpose: Calculate stock coverage using verified,
#          unexpired batches and recent sales velocity.
# Method: GET
# Endpoint: /inventory/stock-coverage
# ============================================================

@app.get("/inventory/stock-coverage")
def get_stock_coverage(
    days: int = 30,
    warning_days: int = 7,
    db: Session = Depends(get_db)
):
    try:
        # Validate parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if warning_days < 1 or warning_days > 90:
            raise HTTPException(
                status_code=400,
                detail="Warning days must be between 1 and 90"
            )

        # Calculate analysis period
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate total sales for each product
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold")
            )
            .filter(
                StockMovement.movement_type == "sale",
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Calculate saleable stock from verified, unexpired batches
        today = date.today()

        batch_subquery = (
            db.query(
                ProductBatch.product_id.label("product_id"),
                func.coalesce(
                    func.sum(ProductBatch.quantity), 0
                ).label("saleable_stock")
            )
            .filter(
                ProductBatch.is_verified == True,
                ProductBatch.expiry_date >= today,
                ProductBatch.quantity > 0
            )
            .group_by(ProductBatch.product_id)
            .subquery()
        )

        # Retrieve active products with recorded and saleable stock
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.quantity.label("recorded_stock"),
                Product.minimum_stock.label("minimum_stock"),
                Product.unit.label("unit"),
                func.coalesce(
                    batch_subquery.c.saleable_stock, 0
                ).label("saleable_stock"),
                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ).label("total_quantity_sold")
            )
            .outerjoin(
                batch_subquery,
                Product.id == batch_subquery.c.product_id
            )
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(Product.is_active == True)
            .order_by(Product.name.asc())
            .all()
        )

        stock_report = []

        for row in results:
            recorded_stock = float(row.recorded_stock or 0)
            saleable_stock = float(row.saleable_stock or 0)
            minimum_stock = float(row.minimum_stock or 0)
            total_sold = float(row.total_quantity_sold or 0)

            average_daily_sales = total_sold / days

            # Estimate remaining days using saleable stock
            if average_daily_sales > 0:
                estimated_days_remaining = (
                    saleable_stock / average_daily_sales
                )
            else:
                estimated_days_remaining = None

            # Determine stock health using saleable stock
            if saleable_stock <= 0:
                stock_status = "out_of_stock"

            elif saleable_stock <= minimum_stock:
                stock_status = "critical"

            elif (
                estimated_days_remaining is not None
                and estimated_days_remaining <= warning_days
            ):
                stock_status = "low_stock"

            else:
                stock_status = "healthy"

            stock_report.append({
                "product_id": row.product_id,
                "product_name": row.product_name,
                "recorded_stock": recorded_stock,
                "saleable_stock": saleable_stock,
                "minimum_stock": minimum_stock,
                "unit": row.unit,
                "total_quantity_sold": total_sold,
                "average_daily_sales": round(
                    average_daily_sales, 2
                ),
                "estimated_days_remaining": (
                    round(estimated_days_remaining, 2)
                    if estimated_days_remaining is not None
                    else None
                ),
                "stock_status": stock_status
            })

        return {
            "analysis_period_days": days,
            "warning_threshold_days": warning_days,
            "total_products": len(stock_report),
            "stock_coverage": stock_report
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to generate stock coverage report"
        )



# ============================================================
# INVENTORY HEALTH SUMMARY API
# Purpose: Provide an overall health report of shop inventory.
# Method: GET
# Endpoint: /inventory/health-summary
# ============================================================

@app.get("/inventory/health-summary")
def get_inventory_health_summary(
    warning_days: int = 7,
    days: int = 30,
    db: Session = Depends(get_db)
):
    try:
        # Validate parameters
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        if warning_days < 1 or warning_days > 90:
            raise HTTPException(
                status_code=400,
                detail="Warning days must be between 1 and 90"
            )

        # Calculate analysis period
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        today = date.today()

        # Calculate sales for each product
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("total_quantity_sold")
            )
            .filter(
                StockMovement.movement_type == "sale",
                StockMovement.created_at >= start_date,
                StockMovement.created_at <= end_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Calculate saleable stock
        saleable_subquery = (
            db.query(
                ProductBatch.product_id.label("product_id"),
                func.sum(ProductBatch.quantity).label("saleable_stock")
            )
            .filter(
                ProductBatch.is_verified == True,
                ProductBatch.expiry_date >= today,
                ProductBatch.quantity > 0
            )
            .group_by(ProductBatch.product_id)
            .subquery()
        )

        # Calculate unverified stock
        unverified_subquery = (
            db.query(
                ProductBatch.product_id.label("product_id"),
                func.sum(ProductBatch.quantity).label("unverified_stock")
            )
            .filter(
                ProductBatch.is_verified == False,
                ProductBatch.quantity > 0
            )
            .group_by(ProductBatch.product_id)
            .subquery()
        )

        # Calculate expired stock
        expired_subquery = (
            db.query(
                ProductBatch.product_id.label("product_id"),
                func.sum(ProductBatch.quantity).label("expired_stock")
            )
            .filter(
                ProductBatch.expiry_date < today,
                ProductBatch.quantity > 0
            )
            .group_by(ProductBatch.product_id)
            .subquery()
        )

        # Retrieve active products and inventory information
        results = (
            db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.quantity.label("recorded_stock"),
                Product.minimum_stock.label("minimum_stock"),
                Product.unit.label("unit"),

                func.coalesce(
                    saleable_subquery.c.saleable_stock, 0
                ).label("saleable_stock"),

                func.coalesce(
                    unverified_subquery.c.unverified_stock, 0
                ).label("unverified_stock"),

                func.coalesce(
                    expired_subquery.c.expired_stock, 0
                ).label("expired_stock"),

                func.coalesce(
                    sales_subquery.c.total_quantity_sold, 0
                ).label("total_quantity_sold")
            )
            .outerjoin(
                saleable_subquery,
                Product.id == saleable_subquery.c.product_id
            )
            .outerjoin(
                unverified_subquery,
                Product.id == unverified_subquery.c.product_id
            )
            .outerjoin(
                expired_subquery,
                Product.id == expired_subquery.c.product_id
            )
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(Product.is_active == True)
            .all()
        )

        # Initialize summary counters
        total_recorded_stock = 0
        total_saleable_stock = 0
        total_unverified_stock = 0
        total_expired_stock = 0

        out_of_stock_products = 0
        critical_stock_products = 0
        low_stock_products = 0
        healthy_products = 0

        products_with_unverified_stock = 0
        products_with_expired_stock = 0

        product_details = []

        for row in results:
            recorded_stock = float(row.recorded_stock or 0)
            saleable_stock = float(row.saleable_stock or 0)
            unverified_stock = float(row.unverified_stock or 0)
            expired_stock = float(row.expired_stock or 0)
            minimum_stock = float(row.minimum_stock or 0)
            total_sold = float(row.total_quantity_sold or 0)

            average_daily_sales = total_sold / days

            if average_daily_sales > 0:
                estimated_days_remaining = (
                    saleable_stock / average_daily_sales
                )
            else:
                estimated_days_remaining = None

            # Determine product stock status
            if saleable_stock <= 0:
                stock_status = "out_of_stock"
                out_of_stock_products += 1

            elif saleable_stock <= minimum_stock:
                stock_status = "critical"
                critical_stock_products += 1

            elif (
                estimated_days_remaining is not None
                and estimated_days_remaining <= warning_days
            ):
                stock_status = "low_stock"
                low_stock_products += 1

            else:
                stock_status = "healthy"
                healthy_products += 1

            # Accumulate stock totals
            total_recorded_stock += recorded_stock
            total_saleable_stock += saleable_stock
            total_unverified_stock += unverified_stock
            total_expired_stock += expired_stock

            if unverified_stock > 0:
                products_with_unverified_stock += 1

            if expired_stock > 0:
                products_with_expired_stock += 1

            product_details.append({
                "product_id": row.product_id,
                "product_name": row.product_name,
                "recorded_stock": recorded_stock,
                "saleable_stock": saleable_stock,
                "unverified_stock": unverified_stock,
                "expired_stock": expired_stock,
                "minimum_stock": minimum_stock,
                "unit": row.unit,
                "total_quantity_sold": total_sold,
                "estimated_days_remaining": (
                    round(estimated_days_remaining, 2)
                    if estimated_days_remaining is not None
                    else None
                ),
                "stock_status": stock_status
            })

        # Return inventory health summary
        return {
            "analysis_period_days": days,
            "warning_threshold_days": warning_days,

            "total_products": len(results),

            "stock_totals": {
                "recorded_stock": round(total_recorded_stock, 2),
                "saleable_stock": round(total_saleable_stock, 2),
                "unverified_stock": round(total_unverified_stock, 2),
                "expired_stock": round(total_expired_stock, 2)
            },

            "product_health": {
                "out_of_stock": out_of_stock_products,
                "critical": critical_stock_products,
                "low_stock": low_stock_products,
                "healthy": healthy_products
            },

            "stock_warnings": {
                "products_with_unverified_stock":
                    products_with_unverified_stock,
                "products_with_expired_stock":
                    products_with_expired_stock
            },

            "products": product_details
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to generate inventory health summary"
        )



# ============================================================
# EXPIRY INTELLIGENCE API
# Purpose: Identify expired and soon-to-expire inventory
#          batches, with quantities and verification status.
# Method: GET
# Endpoint: /inventory/expiry-intelligence
# Expiry windows: 7, 15, 30 and 60 days
# ============================================================

@app.get("/inventory/expiry-intelligence")
def get_expiry_intelligence(
    db: Session = Depends(get_db)
):
    try:
        # Use the current calendar date
        today = datetime.now(timezone.utc).date()

        # Fetch batches belonging to active products
        results = (
            db.query(ProductBatch, Product)
            .join(
                Product,
                ProductBatch.product_id == Product.id
            )
            .filter(
                Product.is_active == True,
                ProductBatch.quantity > 0
            )
            .order_by(
                ProductBatch.expiry_date.asc(),
                Product.name.asc()
            )
            .all()
        )

        # Initialize expiry categories
        categories = {
            "expired": [],
            "expiring_within_7_days": [],
            "expiring_8_to_15_days": [],
            "expiring_16_to_30_days": [],
            "expiring_31_to_60_days": [],
            "beyond_60_days": []
        }

        # Analyze every batch
        for batch, product in results:

            days_remaining = (
                batch.expiry_date - today
            ).days

            quantity = float(batch.quantity or 0)

            # Classify expiry window
            if days_remaining < 0:
                category = "expired"

            elif days_remaining <= 7:
                category = "expiring_within_7_days"

            elif days_remaining <= 15:
                category = "expiring_8_to_15_days"

            elif days_remaining <= 30:
                category = "expiring_16_to_30_days"

            elif days_remaining <= 60:
                category = "expiring_31_to_60_days"

            else:
                category = "beyond_60_days"

            # Build batch information
            batch_details = {
                "batch_id": batch.id,
                "product_id": product.id,
                "product_name": product.name,
                "batch_number": batch.batch_number,
                "quantity": quantity,
                "unit": product.unit,
                "expiry_date": batch.expiry_date.isoformat(),
                "days_remaining": days_remaining,
                "is_verified": bool(batch.is_verified),
                "expiry_category": category
            }

            categories[category].append(batch_details)

        # Build summary for each category
        summary = {}

        for category, batches in categories.items():

            summary[category] = {
                "batch_count": len(batches),
                "product_count": len({
                    item["product_id"]
                    for item in batches
                })
            }

        # Calculate overall statistics
        total_batches = sum(
            len(batches)
            for batches in categories.values()
        )

        expired_batches = len(categories["expired"])

        expiring_within_60_days = sum(
            len(categories[key])
            for key in [
                "expiring_within_7_days",
                "expiring_8_to_15_days",
                "expiring_16_to_30_days",
                "expiring_31_to_60_days"
            ]
        )

        # Return expiry intelligence report
        return {
            "report_date": today.isoformat(),
            "total_batches": total_batches,
            "expired_batches": expired_batches,
            "expiring_within_60_days":
                expiring_within_60_days,
            "summary": summary,
            "batches": categories
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to generate expiry intelligence report"
        )



# ==========================================
# APPROVED EXPIRY DISPOSAL EXECUTION API
# Purpose:
# Execute an owner-approved disposal request.
# Deduct stock exactly once and create an audit
# movement record.
#
# Method: PUT
# Endpoint: /expiry-records/{record_id}/execute-disposal
# ==========================================

@app.put("/expiry-records/{record_id}/execute-disposal")
def execute_expiry_disposal(
    record_id: int,
    db: Session = Depends(get_db)
):
    try:
        # Validate record ID
        if record_id <= 0:
            raise HTTPException(400, "Invalid record ID")

        # Find request to identify its product and batch
        record_reference = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).first()

        if not record_reference:
            raise HTTPException(404, "Expiry record not found")

        # Find batch reference
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

        # Lock batch second
        batch = db.query(ProductBatch).filter(
            ProductBatch.id == record_reference.batch_id,
            ProductBatch.product_id == product.id
        ).with_for_update().first()

        if not batch:
            raise HTTPException(404, "Batch not found")

        # Lock expiry record last
        record = db.query(ExpiryRecord).filter(
            ExpiryRecord.id == record_id
        ).with_for_update().first()

        if not record:
            raise HTTPException(404, "Expiry record not found")

        # Only disposal actions are allowed
        if record.action != "disposal":
            raise HTTPException(
                400,
                "This record is not a disposal request"
            )

        # Owner approval is mandatory
        if record.approval_status != "approved":
            raise HTTPException(
                403,
                "Owner approval is required before disposal"
            )

        # Prevent duplicate execution
        if record.action_status == "completed":
            raise HTTPException(
                409,
                "This disposal has already been completed"
            )

        if record.action_status != "requested":
            raise HTTPException(
                400,
                "This disposal request cannot be executed"
            )

        # Confirm the batch is still expired
        if batch.expiry_date >= date.today():
            raise HTTPException(
                400,
                "This batch is no longer eligible for expired-stock disposal"
            )

        # Validate requested quantity
        quantity = float(record.quantity)

        if not math.isfinite(quantity) or quantity <= 0:
            raise HTTPException(
                400,
                "Invalid disposal quantity"
            )

        if quantity > batch.quantity:
            raise HTTPException(
                400,
                "Disposal quantity exceeds remaining batch stock"
            )

        if quantity > product.quantity:
            raise HTTPException(
                400,
                "Disposal quantity exceeds product stock"
            )

        # Capture stock before deduction
        previous_stock = product.quantity
        previous_batch_quantity = batch.quantity

        # Deduct stock
        batch.quantity -= quantity
        product.quantity -= quantity

        # Create inventory audit movement
        movement = StockMovement(
            product_id=product.id,
            movement_type="disposal",
            quantity_change=-quantity,
            quantity_before=previous_stock,
            quantity_after=product.quantity,
            reason=(
                f"Approved expired stock disposal: "
                f"{record.reason or 'Expired batch'}"
            ),
            performed_by=record.approved_by,
            reference_type="expiry_record",
            reference_id=record.id
        )

        db.add(movement)

        # Mark action as completed
        record.action_status = "completed"
        record.action_completed_at = datetime.now(timezone.utc)

        db.commit()

        db.refresh(record)
        db.refresh(product)
        db.refresh(batch)
        db.refresh(movement)

        return {
            "message": "Approved expired stock disposed successfully",
            "record_id": record.id,
            "product_id": product.id,
            "product_name": product.name,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "action": record.action,
            "approval_status": record.approval_status,
            "action_status": record.action_status,
            "disposed_quantity": quantity,
            "previous_product_stock": previous_stock,
            "current_product_stock": product.quantity,
            "previous_batch_quantity": previous_batch_quantity,
            "remaining_batch_quantity": batch.quantity,
            "movement_id": movement.id,
            "action_completed_at": record.action_completed_at
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()
        print("Disposal execution error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to execute expiry disposal"
        )


# ==========================================
# EXPIRY ACTION DASHBOARD API
# Purpose:
# 1. Display all expiry action requests.
# 2. Summarize pending owner approvals.
# 3. Track disposal and supplier return stages.
# 4. Identify completed and rejected actions.
# 5. Identify inconsistent historical records.
#
# Method: GET
# Endpoint: /expiry-records/dashboard
# ==========================================

@app.get("/expiry-records/dashboard")
def get_expiry_action_dashboard(
    limit: int = 100,
    db: Session = Depends(get_db)
):
    try:
        # Validate limit
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 500
        ):
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 500"
            )

        # Fetch expiry records with linked product,
        # batch and supplier information.
        records = (
            db.query(
                ExpiryRecord,
                ProductBatch,
                Product,
                Supplier
            )
            .join(
                ProductBatch,
                ExpiryRecord.batch_id == ProductBatch.id
            )
            .join(
                Product,
                ProductBatch.product_id == Product.id
            )
            .outerjoin(
                Supplier,
                ExpiryRecord.supplier_id == Supplier.id
            )
            .order_by(ExpiryRecord.recorded_at.desc())
            .limit(limit)
            .all()
        )

        # Dashboard sections
        pending_approvals = []
        approved_disposals = []
        supplier_response_pending = []
        awaiting_pickup = []
        awaiting_credit = []
        completed_actions = []
        rejected_cancelled = []

        # Process each record
        for record, batch, product, supplier in records:

            # Identify inconsistent historical data
            data_warnings = []

            if (
                record.action == "supplier_return"
                and not record.supplier_id
            ):
                data_warnings.append(
                    "Supplier return has no linked supplier"
                )

            if (
                record.return_status == "credited"
                and record.action_status != "completed"
            ):
                data_warnings.append(
                    "Credit is recorded but action_status is not completed"
                )

            if (
                record.return_status in ["accepted", "picked_up", "credited"]
                and record.approval_status != "approved"
            ):
                data_warnings.append(
                    "Supplier return progressed without approved owner status"
                )

            if (
                record.action_status == "completed"
                and record.action_completed_at is None
            ):
                data_warnings.append(
                    "Completed action is missing completion timestamp"
                )

            # Build dashboard item
            item = {
                "record_id": record.id,
                "product_id": product.id,
                "product_name": product.name,
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "quantity": record.quantity,
                "action": record.action,
                "reason": record.reason,
                "approval_status": record.approval_status,
                "action_status": record.action_status,
                "return_status": record.return_status,
                "supplier_id": record.supplier_id,
                "supplier_name": (
                    supplier.name
                    if supplier
                    else record.supplier_name
                ),
                "approved_by": record.approved_by,
                "owner_approved_at": record.owner_approved_at,
                "supplier_accepted_at": record.approved_at,
                "picked_up_at": record.picked_up_at,
                "credit_amount": record.credit_amount,
                "credited_at": record.credited_at,
                "action_completed_at": record.action_completed_at,
                "recorded_at": record.recorded_at,
                "data_warnings": data_warnings
            }

            # ----------------------------------
            # 1. Rejected or cancelled requests
            # ----------------------------------
            if (
                record.approval_status == "rejected"
                or record.action_status == "cancelled"
                or record.return_status == "rejected"
            ):
                rejected_cancelled.append(item)

            # ----------------------------------
            # 2. Supplier credit already recorded
            # Treat as completed even if older
            # records have inconsistent statuses.
            # ----------------------------------
            elif (
                record.action == "supplier_return"
                and record.return_status == "credited"
            ):
                completed_actions.append(item)

            # ----------------------------------
            # 3. Completed disposal requests
            # ----------------------------------
            elif (
                record.action == "disposal"
                and record.action_status == "completed"
            ):
                completed_actions.append(item)

            # ----------------------------------
            # 4. Requests awaiting owner approval
            # ----------------------------------
            elif (
                record.approval_status == "pending"
                and record.action_status == "requested"
            ):
                pending_approvals.append(item)

            # ----------------------------------
            # 5. Approved disposal awaiting execution
            # ----------------------------------
            elif (
                record.action == "disposal"
                and record.approval_status == "approved"
                and record.action_status == "requested"
            ):
                approved_disposals.append(item)

            # ----------------------------------
            # 6. Supplier return awaiting response
            # ----------------------------------
            elif (
                record.action == "supplier_return"
                and record.approval_status == "approved"
                and record.return_status == "pending"
                and record.action_status == "requested"
            ):
                supplier_response_pending.append(item)

            # ----------------------------------
            # 7. Supplier accepted, pickup pending
            # ----------------------------------
            elif (
                record.action == "supplier_return"
                and record.approval_status == "approved"
                and record.return_status == "accepted"
                and record.action_status == "requested"
            ):
                awaiting_pickup.append(item)

            # ----------------------------------
            # 8. Pickup completed, credit pending
            # ----------------------------------
            elif (
                record.action == "supplier_return"
                and record.return_status == "picked_up"
                and record.action_status == "completed"
            ):
                awaiting_credit.append(item)

        # Dashboard summary
        summary = {
            "total_records": len(records),
            "pending_approvals": len(pending_approvals),
            "approved_disposals": len(approved_disposals),
            "supplier_response_pending": len(supplier_response_pending),
            "awaiting_pickup": len(awaiting_pickup),
            "awaiting_credit": len(awaiting_credit),
            "completed_actions": len(completed_actions),
            "rejected_cancelled": len(rejected_cancelled)
        }

        return {
            "message": "Expiry action dashboard retrieved successfully",
            "summary": summary,
            "dashboard": {
                "pending_approvals": pending_approvals,
                "approved_disposals": approved_disposals,
                "supplier_response_pending": supplier_response_pending,
                "awaiting_pickup": awaiting_pickup,
                "awaiting_credit": awaiting_credit,
                "completed_actions": completed_actions,
                "rejected_cancelled": rejected_cancelled
            }
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Expiry dashboard error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve expiry action dashboard"
        )



# ==========================================
# EXPIRY ACTION FILTERING API
# Purpose:
# 1. Filter expiry records by action type.
# 2. Filter by owner approval status.
# 3. Filter by supplier and date range.
# 4. Support pagination.
# 5. Return expiry action details and total count.
#
# Method: GET
# Endpoint: /expiry-records/filter
# ==========================================

@app.get("/expiry-records/filter")
def filter_expiry_records(
    action: str | None = None,
    approval_status: str | None = None,
    supplier_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    try:
        # Validate action
        valid_actions = ["disposal", "supplier_return"]

        if action is not None and action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail="Invalid action type"
            )

        # Validate approval status
        valid_approvals = [
            "pending",
            "approved",
            "rejected"
        ]

        if (
            approval_status is not None
            and approval_status not in valid_approvals
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid approval status"
            )

        # Validate supplier ID
        if supplier_id is not None and supplier_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Supplier ID must be positive"
            )

        # Validate pagination
        if limit < 1 or limit > 500:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 500"
            )

        if offset < 0:
            raise HTTPException(
                status_code=400,
                detail="Offset cannot be negative"
            )

        # Validate date range
        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be after end date"
            )

        # Build base query
        query = (
            db.query(
                ExpiryRecord,
                ProductBatch,
                Product,
                Supplier
            )
            .join(
                ProductBatch,
                ExpiryRecord.batch_id == ProductBatch.id
            )
            .join(
                Product,
                ProductBatch.product_id == Product.id
            )
            .outerjoin(
                Supplier,
                ExpiryRecord.supplier_id == Supplier.id
            )
        )

        # Apply optional filters
        if action is not None:
            query = query.filter(
                ExpiryRecord.action == action
            )

        if approval_status is not None:
            query = query.filter(
                ExpiryRecord.approval_status == approval_status
            )

        if supplier_id is not None:
            query = query.filter(
                ExpiryRecord.supplier_id == supplier_id
            )

        if start_date is not None:
            query = query.filter(
                func.date(ExpiryRecord.recorded_at) >= start_date
            )

        if end_date is not None:
            query = query.filter(
                func.date(ExpiryRecord.recorded_at) <= end_date
            )

        # Count all matching records
        total_matching = query.count()

        # Fetch requested page
        records = (
            query
            .order_by(
                ExpiryRecord.recorded_at.desc(),
                ExpiryRecord.id.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        results = []

        for record, batch, product, supplier in records:

            results.append({
                "record_id": record.id,
                "product_id": product.id,
                "product_name": product.name,
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "quantity": record.quantity,
                "action": record.action,
                "reason": record.reason,
                "approval_status": record.approval_status,
                "action_status": record.action_status,
                "return_status": record.return_status,
                "supplier_id": record.supplier_id,
                "supplier_name": (
                    supplier.name
                    if supplier
                    else record.supplier_name
                ),
                "approved_by": record.approved_by,
                "owner_approved_at": record.owner_approved_at,
                "supplier_accepted_at": record.approved_at,
                "picked_up_at": record.picked_up_at,
                "credit_amount": record.credit_amount,
                "credited_at": record.credited_at,
                "action_completed_at": record.action_completed_at,
                "recorded_at": record.recorded_at
            })

        return {
            "message": "Expiry records filtered successfully",
            "filters": {
                "action": action,
                "approval_status": approval_status,
                "supplier_id": supplier_id,
                "start_date": start_date,
                "end_date": end_date
            },
            "pagination": {
                "total_matching": total_matching,
                "limit": limit,
                "offset": offset,
                "returned": len(results),
                "has_more": (
                    offset + len(results) < total_matching
                )
            },
            "records": results
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Expiry filtering error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to filter expiry records"
        )




# ==========================================
# DEAD STOCK DETECTION API
# Purpose:
# 1. Identify products with no sales in 30 days.
# 2. Exclude newly added products.
# 3. Calculate stock quantity and blocked stock value.
# 4. Help shop owners identify dead stock.
#
# Method: GET
# Endpoint: /inventory/intelligence/dead-stock
# ==========================================

@app.get("/inventory/intelligence/dead-stock")
def get_dead_stock_products(
    db: Session = Depends(get_db)
):
    try:
        # Analyse the last 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        # Calculate total units sold per product
        # using existing stock movement records.
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("units_sold")
            )
            .filter(
                StockMovement.movement_type == "sale",
                StockMovement.quantity_change < 0,
                StockMovement.created_at >= cutoff_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Find active products that:
        # 1. Have positive stock.
        # 2. Are at least 30 days old.
        # 3. Have zero sales in the last 30 days.
        products = (
            db.query(Product)
            .outerjoin(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(
                Product.is_active.is_(True),
                Product.quantity > 0,
                Product.created_at <= cutoff_date,
                func.coalesce(
                    sales_subquery.c.units_sold, 0
                ) == 0
            )
            .order_by(Product.quantity.desc())
            .all()
        )

        dead_stock_products = []

        total_dead_stock_units = 0
        total_dead_stock_value = 0.0

        for product in products:

            quantity = float(product.quantity or 0)
            purchase_price = float(product.purchase_price or 0)

            stock_value = quantity * purchase_price

            total_dead_stock_units += quantity
            total_dead_stock_value += stock_value

            dead_stock_products.append({
                "product_id": product.id,
                "product_name": product.name,
                "category": product.category,
                "current_stock": product.quantity,
                "unit": product.unit,
                "purchase_price": purchase_price,
                "estimated_stock_value": round(stock_value, 2),
                "analysis_period_days": 30,
                "sales_in_period": 0,
                "recommendation": (
                    "Review stock and consider reducing "
                    "future purchases or checking supplier "
                    "return options."
                )
            })

        return {
            "message": "Dead stock analysis completed successfully",
            "analysis_period_days": 30,
            "summary": {
                "dead_stock_products": len(dead_stock_products),
                "total_dead_stock_units": total_dead_stock_units,
                "total_dead_stock_value": round(
                    total_dead_stock_value, 2
                )
            },
            "dead_stock_products": dead_stock_products
        }

    except Exception as error:
        print("Dead stock detection error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to complete dead stock analysis"
        )

# ==========================================
# INVENTORY INTELLIGENCE DATA READINESS API
# Purpose:
# 1. Check product age and sales history.
# 2. Count products with at least 30 days of history.
# 3. Identify products with and without recent sales.
# 4. Calculate total units sold in the last 30 days.
# 5. Assess readiness for inventory intelligence.
#
# Method: GET
# Endpoint: /inventory/intelligence/data-readiness
# ==========================================

@app.get("/inventory/intelligence/data-readiness")
def get_inventory_data_readiness(
    db: Session = Depends(get_db)
):
    try:
        # Fixed analysis period: 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        # Total active products
        total_active_products = (
            db.query(func.count(Product.id))
            .filter(Product.is_active.is_(True))
            .scalar() or 0
        )

        # Products with at least 30 days of history
        mature_products = (
            db.query(func.count(Product.id))
            .filter(
                Product.is_active.is_(True),
                Product.created_at <= cutoff_date
            )
            .scalar() or 0
        )

        # Products younger than 30 days
        new_products = total_active_products - mature_products

        # Sales summary for the last 30 days
        sales_summary = (
            db.query(
                func.count(
                    func.distinct(StockMovement.product_id)
                ).label("products_with_sales"),
                func.coalesce(
                    func.sum(-StockMovement.quantity_change),
                    0
                ).label("total_units_sold"),
                func.min(
                    StockMovement.created_at
                ).label("first_sale_record")
            )
            .join(
                Product,
                Product.id == StockMovement.product_id
            )
            .filter(
                Product.is_active.is_(True),
                StockMovement.movement_type == "sale",
                StockMovement.quantity_change < 0,
                StockMovement.created_at >= cutoff_date
            )
            .first()
        )

        products_with_sales = int(
            sales_summary.products_with_sales or 0
        )

        total_units_sold = float(
            sales_summary.total_units_sold or 0
        )

        # Products without recorded sales in the period
        products_without_sales = max(
            total_active_products - products_with_sales,
            0
        )

        # Mature products with recent sales
        mature_products_with_sales = (
            db.query(
                func.count(func.distinct(Product.id))
            )
            .join(
                StockMovement,
                StockMovement.product_id == Product.id
            )
            .filter(
                Product.is_active.is_(True),
                Product.created_at <= cutoff_date,
                StockMovement.movement_type == "sale",
                StockMovement.quantity_change < 0,
                StockMovement.created_at >= cutoff_date
            )
            .scalar() or 0
        )

        mature_products_without_sales = max(
            mature_products - mature_products_with_sales,
            0
        )

        # Determine data readiness
        if mature_products == 0:
            readiness_status = "insufficient_history"

            readiness_message = (
                "No active products have completed "
                "the 30-day history period."
            )

        elif total_units_sold == 0:
            readiness_status = "sales_tracking_needs_validation"

            readiness_message = (
                "Mature products are available, but no sales "
                "were recorded in the last 30 days. "
                "Verify sales recording before relying on "
                "dead-stock or fast-moving classifications."
            )

        else:
            readiness_status = "ready_for_initial_detection"

            readiness_message = (
                "Product age and recent sales data are available "
                "for initial inventory intelligence analysis. "
                "Validate sales coverage before treating "
                "recommendations as reliable."
            )

        return {
            "message": "Inventory data readiness retrieved successfully",

            "analysis_period_days": 30,

            "summary": {
                "total_active_products": total_active_products,
                "mature_products": mature_products,
                "new_products": new_products,
                "products_with_sales": products_with_sales,
                "products_without_sales": products_without_sales,
                "mature_products_with_sales": mature_products_with_sales,
                "mature_products_without_sales": mature_products_without_sales,
                "total_units_sold_last_30_days": total_units_sold,
                "first_sale_record_in_period": (
                    sales_summary.first_sale_record
                )
            },

            "readiness": {
                "status": readiness_status,
                "message": readiness_message
            }
        }

    except Exception as error:
        print("Inventory data readiness error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve inventory data readiness"
        )



# ==========================================
# FAST-MOVING PRODUCT DETECTION API
# Purpose:
# 1. Analyse product sales over the last 30 days.
# 2. Calculate average daily sales.
# 3. Calculate current stock coverage in days.
# 4. Rank products by sales quantity.
# 5. Identify products needing replenishment.
# 6. Avoid classifying products with insufficient history.
#
# Method: GET
# Endpoint: /inventory/intelligence/fast-moving
# ==========================================

@app.get("/inventory/intelligence/fast-moving")
def get_fast_moving_products(
    db: Session = Depends(get_db)
):
    try:
        # Fixed analysis period: 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        # Count active products with at least 30 days of history
        mature_products = (
            db.query(func.count(Product.id))
            .filter(
                Product.is_active.is_(True),
                Product.created_at <= cutoff_date
            )
            .scalar() or 0
        )

        # Aggregate sales quantities for active products
        sales_subquery = (
            db.query(
                StockMovement.product_id.label("product_id"),
                func.sum(
                    -StockMovement.quantity_change
                ).label("units_sold")
            )
            .join(
                Product,
                Product.id == StockMovement.product_id
            )
            .filter(
                Product.is_active.is_(True),
                StockMovement.movement_type == "sale",
                StockMovement.quantity_change < 0,
                StockMovement.created_at >= cutoff_date
            )
            .group_by(StockMovement.product_id)
            .subquery()
        )

        # Calculate total observed sales, including
        # products that are not yet mature enough.
        observed_sales = (
            db.query(
                func.coalesce(
                    func.sum(sales_subquery.c.units_sold),
                    0
                )
            )
            .scalar() or 0
        )

        # Analyse only mature products with recorded sales
        products = (
            db.query(
                Product,
                sales_subquery.c.units_sold
            )
            .join(
                sales_subquery,
                Product.id == sales_subquery.c.product_id
            )
            .filter(
                Product.is_active.is_(True),
                Product.created_at <= cutoff_date,
                sales_subquery.c.units_sold > 0
            )
            .order_by(
                sales_subquery.c.units_sold.desc()
            )
            .all()
        )

        fast_moving_candidates = []

        total_eligible_units_sold = 0

        for product, units_sold in products:

            units_sold = float(units_sold or 0)
            current_stock = float(product.quantity or 0)

            # Average daily sales over 30 days
            average_daily_sales = units_sold / 30

            # Calculate stock coverage
            stock_coverage_days = (
                current_stock / average_daily_sales
                if average_daily_sales > 0
                else None
            )

            # Replenishment priority
            if current_stock <= 0:
                replenishment_priority = "urgent"

            elif stock_coverage_days <= 7:
                replenishment_priority = "high"

            elif stock_coverage_days <= 14:
                replenishment_priority = "medium"

            else:
                replenishment_priority = "normal"

            total_eligible_units_sold += units_sold

            fast_moving_candidates.append({
                "product_id": product.id,
                "product_name": product.name,
                "category": product.category,
                "current_stock": product.quantity,
                "unit": product.unit,
                "units_sold_last_30_days": units_sold,
                "average_daily_sales": round(
                    average_daily_sales, 2
                ),
                "stock_coverage_days": round(
                    stock_coverage_days, 2
                ) if stock_coverage_days is not None else None,
                "replenishment_priority": replenishment_priority,
                "purchase_price": float(
                    product.purchase_price or 0
                )
            })

        # Determine analysis readiness
        if mature_products == 0:
            readiness_status = "insufficient_history"

            readiness_message = (
                "No active products have completed "
                "the 30-day history period. "
                "Fast-moving classification is not reliable yet."
            )

        elif not fast_moving_candidates:
            readiness_status = "no_sales_detected"

            readiness_message = (
                "Mature products are available, but no sales "
                "were recorded for them in the last 30 days."
            )

        else:
            readiness_status = "analysis_available"

            readiness_message = (
                "Eligible products have been ranked by sales "
                "quantity. These are fast-moving candidates "
                "and should be reviewed before purchase decisions."
            )

        return {
            "message": "Fast-moving product analysis completed successfully",

            "analysis_period_days": 30,

            "readiness": {
                "status": readiness_status,
                "message": readiness_message
            },

            "summary": {
                "mature_products": mature_products,
                "fast_moving_candidates": len(
                    fast_moving_candidates
                ),
                "total_eligible_units_sold": total_eligible_units_sold,
                "total_observed_units_sold": float(observed_sales)
            },

            "fast_moving_products": fast_moving_candidates
        }

    except Exception as error:
        print("Fast-moving detection error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to complete fast-moving product analysis"
        )






# ---------------------------------------------------------
# API: Sales Analytics Summary
# Method: GET
# Endpoint: /analytics/sales/summary
# Purpose:
# 1. Calculate total sales revenue for a selected period.
# 2. Count completed sales bills.
# 3. Calculate total quantity of products sold.
# 4. Calculate average bill value.
# 5. Provide a summary for the analytics dashboard.
# ---------------------------------------------------------

@app.get("/analytics/sales/summary")
def get_sales_analytics_summary(
    days: int = 30,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    try:
        # Validate analysis period
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Calculate revenue and number of bills
        sales_summary = db.query(
            func.count(Sale.id).label("total_bills"),
            func.coalesce(
                func.sum(Sale.total_amount), 0
            ).label("total_revenue")
        ).filter(
            Sale.shop_id == shop_id,
            Sale.created_at >= start_date,
            Sale.created_at <= end_date
        ).first()

        # Calculate total quantity of products sold
        total_items_sold = db.query(
            func.coalesce(
                func.sum(SaleItem.quantity), 0
            )
        ).join(
            Sale,
            Sale.id == SaleItem.sale_id
        ).filter(
            Sale.shop_id == shop_id,
            Sale.created_at >= start_date,
            Sale.created_at <= end_date
        ).scalar()

        # Convert database results
        total_bills = int(sales_summary.total_bills or 0)
        total_revenue = float(sales_summary.total_revenue or 0)
        total_items_sold = float(total_items_sold or 0)

        # Calculate average bill value
        average_bill_value = (
            total_revenue / total_bills
            if total_bills > 0
            else 0
        )

        return {
            "message": "Sales analytics summary retrieved successfully",
            "analysis_period_days": days,
            "summary": {
                "total_revenue": round(total_revenue, 2),
                "total_bills": total_bills,
                "total_items_sold": round(total_items_sold, 2),
                "average_bill_value": round(
                    average_bill_value, 2
                )
            },
            "period": {
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except HTTPException:
        raise

    except Exception as error:
        db.rollback()
        print("Sales analytics error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve sales analytics summary"
        )

# ---------------------------------------------------------
# API: Daily Sales Analytics
# Method: GET
# Endpoint: /analytics/sales/daily
# Purpose:
# 1. Calculate daily sales revenue.
# 2. Count bills recorded each day.
# 3. Calculate total product quantities sold daily.
# 4. Identify the highest-revenue day.
# 5. Provide daily data for dashboard charts.
# ---------------------------------------------------------

@app.get("/analytics/sales/daily")
def get_daily_sales_analytics(
    days: int = 7,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    try:
        # Validate analysis period
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Fetch sales within the selected period
        sales = db.query(Sale).filter(
            Sale.shop_id == shop_id,
            Sale.created_at >= start_date,
            Sale.created_at <= end_date
        ).order_by(
            Sale.created_at.asc()
        ).all()

        # Prepare daily summary
        daily_data = {}

        for sale in sales:
            sale_date = sale.created_at.date().isoformat()

            if sale_date not in daily_data:
                daily_data[sale_date] = {
                    "date": sale_date,
                    "revenue": 0.0,
                    "total_bills": 0,
                    "items_sold": 0.0
                }

            daily_data[sale_date]["revenue"] += float(
                sale.total_amount or 0
            )

            daily_data[sale_date]["total_bills"] += 1

            for item in sale.items:
                daily_data[sale_date]["items_sold"] += float(
                    item.quantity or 0
                )

        # Sort daily records
        daily_sales = sorted(
            daily_data.values(),
            key=lambda item: item["date"]
        )

        # Round monetary and quantity values
        for day in daily_sales:
            day["revenue"] = round(day["revenue"], 2)
            day["items_sold"] = round(day["items_sold"], 2)

        # Find highest-revenue day
        highest_sales_day = (
            max(
                daily_sales,
                key=lambda item: item["revenue"]
            )
            if daily_sales
            else None
        )

        return {
            "message": "Daily sales analytics retrieved successfully",
            "analysis_period_days": days,
            "total_days_with_sales": len(daily_sales),
            "daily_sales": daily_sales,
            "highest_sales_day": highest_sales_day
        }

    except HTTPException:
        raise

    except Exception as error:
        db.rollback()
        print("Daily sales analytics error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve daily sales analytics"
        )

# ---------------------------------------------------------
# API: Product-wise Sales Performance
# Method: GET
# Endpoint: /analytics/sales/products
# Purpose:
# 1. Identify the best-selling products.
# 2. Calculate quantity sold for each product.
# 3. Calculate revenue generated by each product.
# 4. Count the number of bills containing each product.
# 5. Rank products based on quantity sold.
# ---------------------------------------------------------

@app.get("/analytics/sales/products")
def get_product_sales_analytics(
    days: int = 30,
    limit: int = 10,
    shop_id: int = Query(..., gt=0),
    membership=Depends(require_shop_staff),
    db: Session = Depends(get_db)
):
    try:
        # Validate analysis period
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=400,
                detail="Days must be between 1 and 365"
            )

        # Validate product limit
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 100"
            )

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Aggregate sales records product-wise
        product_sales = db.query(
            SaleItem.product_id.label("product_id"),
            SaleItem.product_name.label("product_name"),
            SaleItem.unit.label("unit"),

            func.sum(
                SaleItem.quantity
            ).label("total_quantity_sold"),

            func.sum(
                SaleItem.subtotal
            ).label("total_revenue"),

            func.count(
                func.distinct(SaleItem.sale_id)
            ).label("total_bills")

        ).join(
            Sale,
            Sale.id == SaleItem.sale_id
        ).filter(
            Sale.shop_id == shop_id,
            Sale.created_at >= start_date,
            Sale.created_at <= end_date
        ).group_by(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.unit
        ).order_by(
            func.sum(SaleItem.quantity).desc(),
            func.sum(SaleItem.subtotal).desc()
        ).limit(limit).all()

        # Prepare product-wise response
        products = []

        for rank, product in enumerate(product_sales, start=1):
            products.append({
                "rank": rank,
                "product_id": product.product_id,
                "product_name": product.product_name,
                "unit": product.unit,
                "total_quantity_sold": round(
                    float(product.total_quantity_sold or 0), 2
                ),
                "total_revenue": round(
                    float(product.total_revenue or 0), 2
                ),
                "total_bills": int(product.total_bills or 0)
            })

        # Return product performance
        return {
            "message": "Product-wise sales analytics retrieved successfully",
            "analysis_period_days": days,
            "total_products_sold": len(products),
            "products": products
        }

    except HTTPException:
        raise

    except Exception as error:
        db.rollback()
        print("Product sales analytics error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve product-wise sales analytics"
        )






# ---------------------------------------------------------
# API: Sales Analytics AI Chat with Performance Monitoring
# Method: POST
# Endpoint: /agents/sales/chat
# Purpose:
# 1. Understand the owner's sales question.
# 2. Retrieve verified sales data.
# 3. Use cache to avoid repeated database queries.
# 4. Generate a fast response.
# 5. Measure execution time of each stage.
# ---------------------------------------------------------

@app.post("/agents/sales/chat")
def sales_analytics_chat(
    question: str = Body(
        ...,
        embed=True,
        min_length=1,
        max_length=1000
    ),
    db: Session = Depends(get_db)
):
    import time

    # Start total execution timer
    total_start = time.perf_counter()

    # Initialize performance measurements
    intent_time = 0.0
    database_time = 0.0
    formatting_time = 0.0
    cache_lookup_time = 0.0
    cache_hit = False

    try:
        # Import sales analytics agent
        from app.agents.sales_analytics_agent import (
            understand_sales_question,
            format_sales_answer
        )

        # Import analytics cache service
        from app.services.sales_analytics_cache import (
            get_cached_analytics,
            set_cached_analytics
        )

        # ---------------------------------------------
        # STAGE 1: Intent Detection
        # ---------------------------------------------

        intent_start = time.perf_counter()

        intent_result = understand_sales_question(question)

        intent_time = (
            time.perf_counter() - intent_start
        ) * 1000

        intent = intent_result.intent
        days = intent_result.days
        limit = intent_result.limit

        # ---------------------------------------------
        # Handle unsupported questions
        # ---------------------------------------------

        if intent == "unknown":

            total_time = (
                time.perf_counter() - total_start
            ) * 1000

            return {
                "message": "Please clarify your sales question.",
                "question": question,
                "intent": intent,
                "answer": (
                    intent_result.clarification
                    or "I can help with sales summaries, daily sales and best-selling products."
                ),
                "analytics_data": None,
                "performance": {
                    "intent_detection_ms": round(intent_time, 2),
                    "cache_hit": False,
                    "cache_lookup_ms": 0,
                    "database_retrieval_ms": 0,
                    "answer_formatting_ms": 0,
                    "total_response_time_ms": round(total_time, 2)
                }
            }

        # ---------------------------------------------
        # STAGE 2: Cache Lookup
        # ---------------------------------------------

        cache_key = f"sales:{intent}:{days}:{limit}"

        cache_start = time.perf_counter()

        analytics_data = get_cached_analytics(cache_key)

        cache_lookup_time = (
            time.perf_counter() - cache_start
        ) * 1000

        if analytics_data is not None:

            cache_hit = True

        else:

            # -----------------------------------------
            # STAGE 3: Database Retrieval
            # -----------------------------------------

            database_start = time.perf_counter()

            if intent == "summary":

                analytics_data = get_sales_analytics_summary(
                    days=days,
                    db=db
                )

            elif intent == "daily":

                analytics_data = get_daily_sales_analytics(
                    days=days,
                    db=db
                )

            elif intent == "products":

                analytics_data = get_product_sales_analytics(
                    days=days,
                    limit=limit,
                    db=db
                )

            else:

                raise HTTPException(
                    status_code=400,
                    detail="Unsupported sales analytics intent."
                )

            database_time = (
                time.perf_counter() - database_start
            ) * 1000

            # -----------------------------------------
            # Store verified database results in cache
            # -----------------------------------------

            set_cached_analytics(
                cache_key=cache_key,
                data=analytics_data
            )

        # ---------------------------------------------
        # STAGE 4: Answer Formatting
        # ---------------------------------------------

        formatting_start = time.perf_counter()

        answer = format_sales_answer(
            question=question,
            intent=intent,
            analytics_data=analytics_data
        )

        formatting_time = (
            time.perf_counter() - formatting_start
        ) * 1000

        # ---------------------------------------------
        # STAGE 5: Total Response Time
        # ---------------------------------------------

        total_time = (
            time.perf_counter() - total_start
        ) * 1000

        # ---------------------------------------------
        # Return complete response and performance data
        # ---------------------------------------------

        return {
            "message": "Sales analytics answer generated successfully",
            "question": question,
            "intent": intent,
            "analysis_period_days": days,
            "answer": answer,
            "analytics_data": analytics_data,
            "performance": {
                "intent_detection_ms": round(intent_time, 2),
                "cache_hit": cache_hit,
                "cache_lookup_ms": round(cache_lookup_time, 2),
                "database_retrieval_ms": round(database_time, 2),
                "answer_formatting_ms": round(formatting_time, 2),
                "total_response_time_ms": round(total_time, 2)
            }
        }

    except HTTPException:
        raise

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except RuntimeError as error:

        print("Sales analytics agent error:", str(error))

        raise HTTPException(
            status_code=502,
            detail="The sales analytics AI agent is temporarily unavailable."
        )

    except Exception as error:

        print("Sales analytics chat error:", str(error))

        raise HTTPException(
            status_code=500,
            detail="Unable to process the sales analytics question."
        )



# ---------------------------------------------------------
# API: Read-only Inventory Agent Chat
# Method: POST
# Endpoint: /agents/inventory/chat
# Purpose:
# 1. Understand the owner's inventory question.
# 2. Retrieve deterministic inventory intelligence from the database.
# 3. Return both structured data and a grounded natural-language answer.
# This endpoint never changes stock or creates purchase orders.
# ---------------------------------------------------------

@app.post("/agents/inventory/chat")
def inventory_agent_chat(
    question: str = Body(
        ...,
        embed=True,
        min_length=1,
        max_length=1000
    ),
    db: Session = Depends(get_db)
):
    import time

    total_start = time.perf_counter()

    try:
        from app.agents.inventory_agent import (
            understand_inventory_question,
            format_inventory_answer,
        )
        from app.services.inventory_intelligence_service import analyze_inventory

        # Stage 1: classify the owner's question using local rules first,
        # with Gemini used only when the question needs language understanding.
        intent_start = time.perf_counter()
        intent_result = understand_inventory_question(question)
        intent_time = (time.perf_counter() - intent_start) * 1000

        intent = intent_result.intent
        days = intent_result.days
        limit = intent_result.limit

        if intent == "unknown":
            return {
                "message": "Please clarify your inventory question.",
                "question": question,
                "intent": intent,
                "answer": (
                    intent_result.clarification
                    or "I can help with low stock, stock coverage, dead stock, "
                       "fast- and slow-moving products, expiry, data readiness, "
                       "and overall inventory health."
                ),
                "analytics_data": None,
                "performance": {
                    "intent_detection_ms": round(intent_time, 2),
                    "database_retrieval_ms": 0,
                    "answer_formatting_ms": 0,
                    "total_response_time_ms": round(
                        (time.perf_counter() - total_start) * 1000, 2
                    ),
                },
            }

        # Stage 2: run read-only SQL calculations. The service is the single
        # source of inventory figures; the agent only explains its results.
        database_start = time.perf_counter()
        analytics_data = analyze_inventory(
            db=db,
            intent=intent,
            days=days,
            limit=limit,
        )
        database_time = (time.perf_counter() - database_start) * 1000

        # Stage 3: format only the values returned by the service.
        formatting_start = time.perf_counter()
        answer = format_inventory_answer(
            question=question,
            intent=intent,
            analytics_data=analytics_data,
        )
        formatting_time = (time.perf_counter() - formatting_start) * 1000

        return {
            "message": "Inventory analysis completed successfully.",
            "question": question,
            "intent": intent,
            "analysis_period_days": analytics_data.get(
                "analysis_period_days",
                analytics_data.get("horizon_days", days),
            ),
            "answer": answer,
            "analytics_data": analytics_data,
            "performance": {
                "intent_detection_ms": round(intent_time, 2),
                "database_retrieval_ms": round(database_time, 2),
                "answer_formatting_ms": round(formatting_time, 2),
                "total_response_time_ms": round(
                    (time.perf_counter() - total_start) * 1000, 2
                ),
            },
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except RuntimeError as error:
        print("Inventory agent understanding error:", str(error))
        raise HTTPException(
            status_code=502,
            detail="The inventory AI agent is temporarily unavailable.",
        )

    except Exception as error:
        print("Inventory agent chat error:", str(error))
        raise HTTPException(
            status_code=500,
            detail="Unable to process the inventory question.",
        )
