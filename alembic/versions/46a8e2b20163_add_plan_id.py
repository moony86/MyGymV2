"""add_plan_id

Revision ID: 46a8e2b20163
Revises: 47706db26107
Create Date: 2026-07-18 23:35:15.694839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46a8e2b20163'
down_revision: Union[str, Sequence[str], None] = '47706db26107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("PRAGMA foreign_keys=OFF;")  # تأكد من وجود هذا السطر
    with op.batch_alter_table('sessions') as batch_op:
        batch_op.add_column(sa.Column('plan_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_sessions_plan_id', 'workout_plans', ['plan_id'], ['id'], ondelete='SET NULL')
    op.execute("PRAGMA foreign_keys=ON;")   # وتأكد من وجود هذا السطر

def downgrade():
    with op.batch_alter_table('sessions') as batch_op:
        batch_op.drop_constraint('fk_sessions_plan_id', type_='foreignkey')
        batch_op.drop_column('plan_id')
