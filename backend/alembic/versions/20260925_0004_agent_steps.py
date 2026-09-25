"""TrayAgent: agent_steps trace table and scan agent/approval columns

Revision ID: 20260925_0004
Revises: 20260510_0003
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0004"
down_revision = "20260510_0003"
branch_labels = None
depends_on = None

SCAN_COLUMNS = [
    ("parent_scan_id", postgresql.UUID(as_uuid=True), {}),
    ("attempt", sa.Integer(), {"server_default": "0"}),
    ("agent_run_id", postgresql.UUID(as_uuid=True), {}),
    ("agent_decision", sa.String(40), {}),
    ("agent_count", sa.Integer(), {}),
    ("agent_reason", sa.Text(), {}),
    ("approved_by", sa.String(80), {}),
    ("approved_at", sa.DateTime(), {}),
]


def upgrade() -> None:
    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_key", sa.String(80), nullable=False, server_default="default"),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(60), nullable=False),
        sa.Column("inputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_key", sa.String(500), nullable=True),
        sa.Column("decision", sa.String(60), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planner", sa.String(20), nullable=False, server_default="deterministic"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
    op.create_index("ix_agent_steps_scan_id", "agent_steps", ["scan_id"])
    for name, type_, kwargs in SCAN_COLUMNS:
        nullable = name != "attempt"
        op.add_column("scan_sessions", sa.Column(name, type_, nullable=nullable, **kwargs))
    op.create_index("idx_scan_sessions_status", "scan_sessions", ["tenant_key", "status"])


def downgrade() -> None:
    op.drop_index("idx_scan_sessions_status", table_name="scan_sessions")
    for name, _type, _kwargs in reversed(SCAN_COLUMNS):
        op.drop_column("scan_sessions", name)
    op.drop_index("ix_agent_steps_scan_id", table_name="agent_steps")
    op.drop_index("ix_agent_steps_run_id", table_name="agent_steps")
    op.drop_table("agent_steps")
