"""Add care_items.va_setting (facility | non_facility) for VA professional charges.

Guarded like 0002: the initial migration's create_all builds the column on a fresh
database, so this only adds it when missing.

Revision ID: 0003_va_setting
Revises: 0002_va_pricing
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_va_setting"
down_revision = "0002_va_pricing"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "va_setting" not in _columns("care_items"):
        op.add_column("care_items", sa.Column(
            "va_setting", sa.String(16), nullable=False,
            server_default="non_facility"))


def downgrade() -> None:
    if "va_setting" in _columns("care_items"):
        op.drop_column("care_items", "va_setting")
