"""add client operation tracking

Revision ID: 4a6b8c1d2e30
Revises: 2f9e1d6a7c41
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a6b8c1d2e30"
down_revision: Union[str, Sequence[str], None] = "2f9e1d6a7c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "client_operations" in inspector.get_table_names():
        return
    op.create_table(
        "client_operations",
        sa.Column("operation_id", sa.TEXT(), nullable=False),
        sa.Column("operation_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.TEXT(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index("ix_client_operations_resource", "client_operations", ["resource_id"])


def downgrade() -> None:
    if "client_operations" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_client_operations_resource", table_name="client_operations")
    op.drop_table("client_operations")