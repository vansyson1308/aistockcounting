"""Scan unit value, so every later count prices its variance from one figure

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
    # Existing scans priced their variance as variance_count * unit_value, so
    # the unit value can be recovered wherever the variance was non-zero.
    op.execute(
        "UPDATE scan_sessions SET unit_value = variance_value / variance_count "
        "WHERE variance_value IS NOT NULL AND variance_count IS NOT NULL "
        "AND variance_count <> 0"
    )


def downgrade() -> None:
    op.drop_column("scan_sessions", "unit_value")
