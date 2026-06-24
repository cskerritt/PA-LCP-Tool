"""Add per-case ZIP3 + system VA pricing-library columns.

The initial migration creates tables from *live* SQLAlchemy metadata
(``create_all``), so a database created fresh after this change already has these
columns. To stay correct for both fresh databases and databases already stamped
at 0001 (created before the columns existed), every change here is guarded by an
inspector check and only applied when missing.

Revision ID: 0002_va_pricing
Revises: 0001_initial
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_va_pricing"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    case_cols = _columns("cases")
    if "geo_zip3" not in case_cols:
        op.add_column("cases", sa.Column("geo_zip3", sa.String(3),
                                         nullable=False, server_default=""))
    if "geo_locality_name" not in case_cols:
        op.add_column("cases", sa.Column("geo_locality_name", sa.String(128),
                                         nullable=False, server_default=""))

    pt_cols = _columns("pricing_tables")
    if "is_system" not in pt_cols:
        op.add_column("pricing_tables", sa.Column(
            "is_system", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "version" not in pt_cols:
        op.add_column("pricing_tables", sa.Column("version", sa.String(32),
                                                  nullable=False, server_default=""))
    if "effective_date" not in pt_cols:
        op.add_column("pricing_tables", sa.Column("effective_date", sa.String(32),
                                                  nullable=False, server_default=""))
    if "ix_pricing_tables_is_system" not in _indexes("pricing_tables"):
        op.create_index("ix_pricing_tables_is_system", "pricing_tables",
                        ["is_system"])
    # Make user_id nullable (system tables have no owner). batch_alter_table is a
    # no-op-safe rebuild on SQLite and a normal ALTER elsewhere.
    with op.batch_alter_table("pricing_tables") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("pricing_tables") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
    if "ix_pricing_tables_is_system" in _indexes("pricing_tables"):
        op.drop_index("ix_pricing_tables_is_system", table_name="pricing_tables")
    for col in ("effective_date", "version", "is_system"):
        if col in _columns("pricing_tables"):
            op.drop_column("pricing_tables", col)
    for col in ("geo_locality_name", "geo_zip3"):
        if col in _columns("cases"):
            op.drop_column("cases", col)
