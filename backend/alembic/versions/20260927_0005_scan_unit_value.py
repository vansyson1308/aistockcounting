"""Scan unit value and review marker

``unit_value`` lets every later count (agent re-run, approval, review) price
its variance from one figure. ``reviewed_at`` marks a human review, so the
agent never re-runs over a human's count. ``version`` is the optimistic lock
that stops a stale write (a review racing an agent run) from overwriting.

Revision ID: 20260927_0005
Revises: 20260925_0004
Create Date: 2026-09-27
"""

import sqlalchemy as sa
from alembic import op

revision = "20260927_0005"
down_revision = "20260925_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_sessions", sa.Column("unit_value", sa.Float(), nullable=True))
    op.add_column("scan_sessions", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "scan_sessions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    # Scans reviewed before this revision: the audit trail has the review.
    op.execute(
        "UPDATE scan_sessions SET reviewed_at = ("
        "SELECT MIN(a.created_at) FROM audit_events a "
        "WHERE a.entity_type = 'scan_session' AND a.action = 'SCAN_REVIEWED' "
        "AND a.entity_id = CAST(scan_sessions.id AS VARCHAR(64))"
        ") WHERE reviewed_at IS NULL"
    )
    # Recover the unit value as variance_value / variance_count, but only where
    # that ratio is still the one priced at creation. Before this revision a
    # review, an approval or an agent re-run changed variance_count without
    # repricing, so those rows stay NULL rather than get a wrong (or negative)
    # unit value; pricing then falls back to the POS / tray master value.
    # A single-shot scan records its variance in SCAN_CREATED: if an agent
    # run changed it since, the ratio is stale even with one run on record.
    op.execute(
        "UPDATE scan_sessions SET unit_value = variance_value / variance_count "
        "WHERE variance_value IS NOT NULL AND variance_count IS NOT NULL "
        "AND variance_count <> 0 "
        "AND variance_value * variance_count >= 0 "
        "AND manual_count IS NULL AND approved_by IS NULL "
        "AND reviewed_at IS NULL "
        "AND (SELECT COUNT(DISTINCT s.run_id) FROM agent_steps s "
        "WHERE s.scan_id = scan_sessions.id) <= 1 "
        "AND NOT EXISTS (SELECT 1 FROM audit_events c "
        "WHERE c.entity_type = 'scan_session' AND c.action = 'SCAN_CREATED' "
        "AND c.entity_id = CAST(scan_sessions.id AS VARCHAR(64)) "
        "AND (c.payload_json ->> 'variance_count') IS NOT NULL "
        "AND (c.payload_json ->> 'variance_count') "
        "<> CAST(scan_sessions.variance_count AS VARCHAR(16)))"
    )


def downgrade() -> None:
    op.drop_column("scan_sessions", "version")
    op.drop_column("scan_sessions", "reviewed_at")
    op.drop_column("scan_sessions", "unit_value")
