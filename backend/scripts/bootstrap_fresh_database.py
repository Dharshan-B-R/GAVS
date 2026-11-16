"""Bootstrap a brand-new KiranaAI database from the current SQLAlchemy models.

Run from any working directory with DATABASE_URL configured:
    python backend/scripts/bootstrap_fresh_database.py

This is ONLY for an empty database. Existing installations must use
    cd backend && alembic upgrade head
Do not run this script against an existing or populated database.
"""
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Register every model used by Alembic before importing main. main calls
# Base.metadata.create_all() during import, so model registration must be
# complete before that happens.
from app.models.shop_membership import ShopMembership  # noqa: F401, E402
from app.models.shop_distributor_connection import ShopDistributorConnection  # noqa: F401, E402
from app.models.shop_invitation import ShopInvitation  # noqa: F401, E402
from app.models.batch_verification import BatchVerification  # noqa: F401, E402
from app.models.customer import Customer  # noqa: F401, E402
from app.models.expiry_record import ExpiryRecord  # noqa: F401, E402
from app.models.khata_transaction import KhataTransaction  # noqa: F401, E402
from app.models.product import Product  # noqa: F401, E402
from app.models.product_batch import ProductBatch  # noqa: F401, E402
from app.models.purchase import Purchase  # noqa: F401, E402
from app.models.purchase_item import PurchaseItem  # noqa: F401, E402
from app.models.purchase_payment import PurchasePayment  # noqa: F401, E402
from app.models.sale import Sale  # noqa: F401, E402
from app.models.sale_item import SaleItem  # noqa: F401, E402
from app.models.shop import Shop  # noqa: F401, E402
from app.models.stock_movement import StockMovement  # noqa: F401, E402
from app.models.supplier import Supplier  # noqa: F401, E402
from app.models.user import User  # noqa: F401, E402
from app.models.shop_purchase_budget import ShopPurchaseBudget  # noqa: F401, E402
from app.models.purchase_proposal import PurchaseProposal  # noqa: F401, E402
from app.models.product_alias import ProductAlias  # noqa: F401, E402
from app.models.festival_event import FestivalEvent  # noqa: F401, E402
from app.models.inventory_availability_snapshot import InventoryAvailabilitySnapshot  # noqa: F401, E402
from app.models.supplier_issue import SupplierIssue  # noqa: F401, E402
from app.models.intelligence_alert import IntelligenceAlert  # noqa: F401, E402
from app.models.intelligence_daily_summary import IntelligenceDailySummary  # noqa: F401, E402
from app.models.recommendation_feedback import RecommendationFeedback  # noqa: F401, E402

import main  # noqa: F401, E402

config = Config(str(BACKEND_DIR / "alembic.ini"))
command.stamp(config, "head")
print("Fresh KiranaAI database created from current models and stamped at Alembic head.")
