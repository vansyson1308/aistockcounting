"""create counts table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260201_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("image_thumbnail", sa.String(length=500), nullable=True),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_count", sa.Integer(), nullable=True),
        sa.Column("confidence_avg", sa.Float(), nullable=True),
        sa.Column("boxes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("staff_id", sa.String(length=50), nullable=True),
        sa.Column("tray_id", sa.String(length=50), nullable=True),
        sa.Column("is_ai_correct", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )

    op.execute("CREATE INDEX idx_counts_created_at ON counts (created_at DESC)")
    op.create_index("idx_counts_staff_id", "counts", ["staff_id"], unique=False)
    op.create_index("idx_counts_tray_id", "counts", ["tray_id"], unique=False)
    op.execute(
        "CREATE INDEX idx_counts_is_ai_correct ON counts (is_ai_correct) WHERE is_ai_correct = false"
    )


def downgrade() -> None:
    op.drop_index("idx_counts_is_ai_correct", table_name="counts")
    op.drop_index("idx_counts_tray_id", table_name="counts")
    op.drop_index("idx_counts_staff_id", table_name="counts")
    op.drop_index("idx_counts_created_at", table_name="counts")
    op.drop_table("counts")
