"""shared folder pickup and schedules

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21 11:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("analysis_key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("run_time", sa.String(length=5), nullable=False),
        sa.Column("weekdays", JSON, nullable=False),
        sa.Column("inputs", JSON, nullable=False),
        sa.Column("parameters", JSON, nullable=False),
        sa.Column("only_when_changed", sa.Boolean(), nullable=False),
        sa.Column("notify", sa.Boolean(), nullable=False),
        sa.Column("last_fired_on", sa.Date(), nullable=True),
        sa.Column("last_signature", sa.String(length=64), nullable=False),
        sa.Column("last_message", sa.Text(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
    )
    op.add_column("data_files", sa.Column("source_path", sa.String(length=1024), nullable=True))
    op.add_column("data_files", sa.Column("source_mtime_ns", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_data_files_source_path"), "data_files", ["source_path"], unique=False)
    op.add_column("analysis_runs", sa.Column("schedule_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_analysis_runs_schedule_id"), "analysis_runs", ["schedule_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_analysis_runs_schedule_id_schedules"),
        "analysis_runs",
        "schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_analysis_runs_schedule_id_schedules"), "analysis_runs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_analysis_runs_schedule_id"), table_name="analysis_runs")
    op.drop_column("analysis_runs", "schedule_id")
    op.drop_index(op.f("ix_data_files_source_path"), table_name="data_files")
    op.drop_column("data_files", "source_mtime_ns")
    op.drop_column("data_files", "source_path")
    op.drop_table("schedules")
