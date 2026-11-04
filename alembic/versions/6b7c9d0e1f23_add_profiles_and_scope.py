"""add simple profile directory and data scope

Revision ID: 6b7c9d0e1f23
Revises: 4a6b8c1d2e30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b7c9d0e1f23"
down_revision: Union[str, Sequence[str], None] = "4a6b8c1d2e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_PROFILE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "profiles" not in tables:
        op.create_table(
            "profiles",
            sa.Column("id", sa.TEXT(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO profiles (id, name, created_at) "
            "VALUES (:id, :name, CURRENT_TIMESTAMP)"
        ).bindparams(id=DEFAULT_PROFILE_ID, name="أنا")
    )

    for table in ("sessions", "workout_plans"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "profile_id" not in columns:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(sa.Column("profile_id", sa.TEXT(), nullable=True))
                batch_op.create_index(f"ix_{table}_profile_id", ["profile_id"])
        op.execute(
            sa.text(f"UPDATE {table} SET profile_id = :profile_id WHERE profile_id IS NULL")
            .bindparams(profile_id=DEFAULT_PROFILE_ID)
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("workout_plans", "sessions"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "profile_id" in columns:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_index(f"ix_{table}_profile_id")
                batch_op.drop_column("profile_id")
    if "profiles" in sa.inspect(bind).get_table_names():
        op.drop_table("profiles")
