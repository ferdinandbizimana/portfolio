"""variance root cause, accuracy progress per file, expiry interventions

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "variance_cases",
        sa.Column("root_cause", sa.String(length=120), server_default="", nullable=False),
    )
    op.add_column("variance_cases", sa.Column("corrected_qty", sa.Float(), nullable=True))
    op.create_table(
        "variance_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_file_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("lines", sa.Integer(), nullable=False),
        sa.Column("system_qty", sa.Float(), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["data_file_id"],
            ["data_files.id"],
            name=op.f("fk_variance_imports_data_file_id_data_files"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variance_imports")),
        sa.UniqueConstraint("data_file_id", name=op.f("uq_variance_imports_data_file_id")),
    )
    op.add_column(
        "expiry_justifications",
        sa.Column("kind", sa.String(length=16), server_default="expired", nullable=False),
    )
    op.add_column(
        "expiry_justifications",
        sa.Column("band", sa.String(length=40), server_default="", nullable=False),
    )
    op.drop_constraint(
        op.f("uq_expiry_justifications_review_id"), "expiry_justifications", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_expiry_justifications_review_id_kind"),
        "expiry_justifications",
        ["review_id", "kind", "material"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_expiry_justifications_review_id_kind"), "expiry_justifications", type_="unique"
    )
    op.execute("DELETE FROM expiry_justifications WHERE kind <> 'expired'")
    op.create_unique_constraint(
        op.f("uq_expiry_justifications_review_id"),
        "expiry_justifications",
        ["review_id", "material"],
    )
    op.drop_column("expiry_justifications", "band")
    op.drop_column("expiry_justifications", "kind")
    op.drop_table("variance_imports")
    op.drop_column("variance_cases", "corrected_qty")
    op.drop_column("variance_cases", "root_cause")
