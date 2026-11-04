"""add rir to sets

Revision ID: 2f9e1d6a7c41
Revises: 208dbc533322
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f9e1d6a7c41"
down_revision: Union[str, Sequence[str], None] = "208dbc533322"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("sets")
    }
    if "rir" in existing_columns:
        return

    with op.batch_alter_table("sets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rir", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("sets")
    }
    if "rir" not in existing_columns:
        return

    with op.batch_alter_table("sets", schema=None) as batch_op:
        batch_op.drop_column("rir")
