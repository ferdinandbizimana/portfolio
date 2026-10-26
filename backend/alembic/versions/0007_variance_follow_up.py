"""spot-check variance follow-up: staff, bin owners, variance cases

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "variance_staff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_digest_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variance_staff")),
    )
    op.create_table(
        "bin_owners",
        sa.Column("storage_bin", sa.String(length=40), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("storage_type", sa.String(length=20), nullable=False),
        sa.Column("storage_section", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["variance_staff.id"],
            name=op.f("fk_bin_owners_staff_id_variance_staff"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("storage_bin", name=op.f("pk_bin_owners")),
    )
    op.create_index(op.f("ix_bin_owners_staff_id"), "bin_owners", ["staff_id"], unique=False)
    op.create_table(
        "variance_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("dedup_key", sa.String(length=300), nullable=False),
        sa.Column("data_file_id", sa.Integer(), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("storage_bin", sa.String(length=40), nullable=False),
        sa.Column("product", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("batch", sa.String(length=40), nullable=False),
        sa.Column("system_qty", sa.Float(), nullable=True),
        sa.Column("counted_qty", sa.Float(), nullable=True),
        sa.Column("difference_qty", sa.Float(), nullable=False),
        sa.Column("found_on", sa.Date(), nullable=True),
        sa.Column("reported_by", sa.String(length=200), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("responsible_unit", sa.String(length=40), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("corrected_by", sa.String(length=200), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["data_file_id"],
            ["data_files.id"],
            name=op.f("fk_variance_cases_data_file_id_data_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["variance_staff.id"],
            name=op.f("fk_variance_cases_staff_id_variance_staff"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variance_cases")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_variance_cases_dedup_key")),
        sa.UniqueConstraint("token", name=op.f("uq_variance_cases_token")),
    )
    op.create_index(op.f("ix_variance_cases_source"), "variance_cases", ["source"], unique=False)
    op.create_index(
        op.f("ix_variance_cases_storage_bin"), "variance_cases", ["storage_bin"], unique=False
    )
    op.create_index(
        op.f("ix_variance_cases_staff_id"), "variance_cases", ["staff_id"], unique=False
    )
    op.create_index(op.f("ix_variance_cases_status"), "variance_cases", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("variance_cases")
    op.drop_index(op.f("ix_bin_owners_staff_id"), table_name="bin_owners")
    op.drop_table("bin_owners")
    op.drop_table("variance_staff")
