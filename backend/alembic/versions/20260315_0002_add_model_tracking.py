"""Add model_version and processing_time_ms columns to counts

Revision ID: 20260315_0002
Revises: 20260201_0001
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260315_0002"
down_revision = "20260201_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("counts", sa.Column("model_version", sa.String(50), nullable=True))
    op.add_column("counts", sa.Column("processing_time_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("counts", "processing_time_ms")
    op.drop_column("counts", "model_version")
