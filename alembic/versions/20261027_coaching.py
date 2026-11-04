"""Private coaching preferences, session reviews and opt-in feedback."""
from alembic import op
import sqlalchemy as sa
revision='20261027_coaching'
down_revision='20261027_plan_options'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('coaching_profiles',sa.Column('profile_id',sa.Text(),sa.ForeignKey('profiles.id',ondelete='CASCADE'),primary_key=True),sa.Column('payload',sa.Text(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_table('session_reviews',sa.Column('session_id',sa.Text(),sa.ForeignKey('sessions.id',ondelete='CASCADE'),primary_key=True),sa.Column('profile_id',sa.Text(),sa.ForeignKey('profiles.id',ondelete='CASCADE'),nullable=False),sa.Column('payload',sa.Text(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_index('ix_session_reviews_profile_id','session_reviews',['profile_id'])
    op.create_table('product_feedback',sa.Column('id',sa.Text(),primary_key=True),sa.Column('profile_id',sa.Text(),sa.ForeignKey('profiles.id',ondelete='CASCADE'),nullable=False),sa.Column('payload',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_product_feedback_profile_id','product_feedback',['profile_id'])

def downgrade():
    op.drop_table('product_feedback');op.drop_table('session_reviews');op.drop_table('coaching_profiles')
