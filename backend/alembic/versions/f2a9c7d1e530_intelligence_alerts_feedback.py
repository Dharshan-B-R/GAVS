"""Add daily intelligence summaries, alerts and recommendation feedback."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f2a9c7d1e530"
down_revision: Union[str, Sequence[str], None] = "e1b4c6d8a920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("dedupe_key", sa.String(180), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "dedupe_key", name="uq_intelligence_alert_shop_dedupe"),
        sa.CheckConstraint("severity IN ('info', 'warning', 'high', 'critical')", name="ck_intelligence_alert_severity"),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_intelligence_alert_status"),
    )
    op.create_index("ix_intelligence_alerts_shop_id", "intelligence_alerts", ["shop_id"])
    op.create_index("ix_intelligence_alerts_product_id", "intelligence_alerts", ["product_id"])

    op.create_table(
        "intelligence_daily_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "summary_date", name="uq_intelligence_daily_summary_shop_date"),
    )
    op.create_index("ix_intelligence_daily_summaries_shop_id", "intelligence_daily_summaries", ["shop_id"])
    op.create_index("ix_intelligence_daily_summaries_summary_date", "intelligence_daily_summaries", ["summary_date"])

    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recommendation_type", sa.String(50), nullable=False, server_default="reorder"),
        sa.Column("recommendation_key", sa.String(180), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("recommended_quantity", sa.Float(), nullable=True),
        sa.Column("actual_quantity", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('accepted', 'dismissed', 'adjusted')", name="ck_recommendation_feedback_decision"),
    )
    op.create_index("ix_recommendation_feedback_shop_id", "recommendation_feedback", ["shop_id"])
    op.create_index("ix_recommendation_feedback_product_id", "recommendation_feedback", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_product_id", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_shop_id", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")

    op.drop_index("ix_intelligence_daily_summaries_summary_date", table_name="intelligence_daily_summaries")
    op.drop_index("ix_intelligence_daily_summaries_shop_id", table_name="intelligence_daily_summaries")
    op.drop_table("intelligence_daily_summaries")

    op.drop_index("ix_intelligence_alerts_product_id", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_shop_id", table_name="intelligence_alerts")
    op.drop_table("intelligence_alerts")
