"""expiry follow-up: monthly reviews and justifications

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expiry_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("mailed_month", sa.String(length=7), nullable=False),
        sa.Column("mailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_expiry_reviews_run_id_analysis_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expiry_reviews")),
        sa.UniqueConstraint("run_id", name=op.f("uq_expiry_reviews_run_id")),
        sa.UniqueConstraint("token", name=op.f("uq_expiry_reviews_token")),
    )
    op.create_table(
        "expiry_justifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("material", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=40), nullable=False),
        sa.Column("plants", sa.String(length=500), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("root_cause", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("justified_by", sa.String(length=200), nullable=False),
        sa.Column("justified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["expiry_reviews.id"],
            name=op.f("fk_expiry_justifications_review_id_expiry_reviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expiry_justifications")),
        sa.UniqueConstraint(
            "review_id", "material", name=op.f("uq_expiry_justifications_review_id")
        ),
    )
    op.create_index(
        op.f("ix_expiry_justifications_review_id"),
        "expiry_justifications",
        ["review_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_expiry_justifications_review_id"), table_name="expiry_justifications")
    op.drop_table("expiry_justifications")
    op.drop_table("expiry_reviews")
