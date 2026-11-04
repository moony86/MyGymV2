"""Persist per-plan alternatives and calendar preferences without shared edits."""
from alembic import op
import sqlalchemy as sa
revision='20261027_plan_options'
down_revision='6b7c9d0e1f23'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('plan_options',sa.Column('plan_id',sa.Text(),sa.ForeignKey('workout_plans.id',ondelete='CASCADE'),primary_key=True),sa.Column('payload',sa.Text(),nullable=False))
def downgrade():
    op.drop_table('plan_options')
