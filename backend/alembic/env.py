
# ==========================================
# KIRANA AI - ALEMBIC DATABASE CONFIGURATION
# Purpose:
# 1. Load the existing database connection.
# 2. Register all SQLAlchemy models.
# 3. Support automatic database migration detection.
# 4. Preserve the existing PostgreSQL database.
# ==========================================

from logging.config import fileConfig

from alembic import context

from app.database import Base, engine

from app.models.shop_membership import ShopMembership
from app.models.shop_distributor_connection import ShopDistributorConnection
from app.models.shop_invitation import ShopInvitation

# Register all existing database models.
# These imports are required for Alembic metadata detection.

from app.models.batch_verification import BatchVerification
from app.models.customer import Customer
from app.models.expiry_record import ExpiryRecord
from app.models.khata_transaction import KhataTransaction
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_payment import PurchasePayment
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.shop import Shop
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.models.user import User
from app.models.shop_purchase_budget import ShopPurchaseBudget
from app.models.purchase_proposal import PurchaseProposal


# Alembic configuration object.
config = context.config

# Configure logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Register all model metadata.
target_metadata = Base.metadata


# ==========================================
# OFFLINE MIGRATION
# Purpose:
# Generate migration SQL without opening
# a live database connection.
# ==========================================

def run_migrations_offline() -> None:
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ==========================================
# ONLINE MIGRATION
# Purpose:
# Connect to the existing database and run
# migrations using the configured connection.
# ==========================================

def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ==========================================
# MIGRATION EXECUTION
# Purpose:
# Select online or offline migration mode.
# ==========================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
