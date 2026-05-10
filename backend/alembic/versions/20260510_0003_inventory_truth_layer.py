"""add inventory truth layer tables

Revision ID: 20260510_0003
Revises: 20260315_0002
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260510_0003"
down_revision = "20260315_0002"
branch_labels = None
depends_on = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("branch_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("pos_branch_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_branches_tenant_code", "branches", ["tenant_key", "branch_code"])

    op.create_table(
        "trays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("branch_code", sa.String(80), nullable=True),
        sa.Column("tray_code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=True),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("unit_value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_trays_tenant_code", "trays", ["tenant_key", "tray_code"])

    op.create_table(
        "catalog_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("unit_value", sa.Float(), nullable=True),
        sa.Column("pos_product_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_catalog_tenant_sku", "catalog_items", ["tenant_key", "sku"])

    op.create_table(
        "pos_inventory_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("branch_code", sa.String(80), nullable=False),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("tray_code", sa.String(80), nullable=True),
        sa.Column("product_name", sa.String(240), nullable=True),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unit_value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(160), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_pos_snapshots_lookup",
        "pos_inventory_snapshots",
        ["tenant_key", "branch_code", "tray_code", "sku"],
    )

    op.create_table(
        "scan_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("branch_code", sa.String(80), nullable=False),
        sa.Column("tray_code", sa.String(80), nullable=False),
        sa.Column("staff_id", sa.String(50), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("image_thumbnail", sa.String(500), nullable=True),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_count", sa.Integer(), nullable=True),
        sa.Column("final_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("variance_count", sa.Integer(), nullable=True),
        sa.Column("variance_value", sa.Float(), nullable=True),
        sa.Column("confidence_avg", sa.Float(), nullable=True),
        sa.Column("boxes_json", _json_type(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_flags", _json_type(), nullable=True),
        sa.Column("is_ai_correct", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending_review"),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_scan_sessions_inbox",
        "scan_sessions",
        ["tenant_key", "branch_code", "status", "created_at"],
    )

    op.create_table(
        "discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("branch_code", sa.String(80), nullable=False),
        sa.Column("tray_code", sa.String(80), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("actual_count", sa.Integer(), nullable=False),
        sa.Column("variance_count", sa.Integer(), nullable=False),
        sa.Column("variance_value", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(50), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_discrepancies_inbox",
        "discrepancies",
        ["tenant_key", "branch_code", "status", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("actor_id", sa.String(80), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=True),
        sa.Column("payload_json", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "pos_sync_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("provider", sa.String(40), nullable=False, server_default="kiotviet"),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processed"),
        sa.Column("payload_json", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_pos_sync_events_key",
        "pos_sync_events",
        ["tenant_key", "provider", "event_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_pos_sync_events_key", table_name="pos_sync_events")
    op.drop_table("pos_sync_events")
    op.drop_table("audit_events")
    op.drop_index("idx_discrepancies_inbox", table_name="discrepancies")
    op.drop_table("discrepancies")
    op.drop_index("idx_scan_sessions_inbox", table_name="scan_sessions")
    op.drop_table("scan_sessions")
    op.drop_index("idx_pos_snapshots_lookup", table_name="pos_inventory_snapshots")
    op.drop_table("pos_inventory_snapshots")
    op.drop_index("idx_catalog_tenant_sku", table_name="catalog_items")
    op.drop_table("catalog_items")
    op.drop_index("idx_trays_tenant_code", table_name="trays")
    op.drop_table("trays")
    op.drop_index("idx_branches_tenant_code", table_name="branches")
    op.drop_table("branches")
