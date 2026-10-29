"""profile: availability, key results, certifications, education, languages

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LISTS = ("highlights", "certifications", "education", "languages")


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column("availability", sa.String(length=200), server_default="", nullable=False),
    )
    json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    for name in LISTS:
        op.add_column(
            "profile", sa.Column(name, json, server_default=sa.text("'[]'"), nullable=False)
        )


def downgrade() -> None:
    for name in reversed(LISTS):
        op.drop_column("profile", name)
    op.drop_column("profile", "availability")
