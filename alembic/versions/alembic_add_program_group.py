"""add program_group_id and day_index to workout_plans

يضيف عمودين على workout_plans لربط خطط الأيام المتعددة (الناتجة عن
GeneratorService) تحت "برنامج" أسبوعي واحد، بدون أي جداول جديدة.
إضافة بحتة، لا تمس أي بيانات موجودة (الخطط اليدوية القديمة تبقى
program_group_id = NULL، وهذا طبيعي ومقبول).

انسخ هذا الملف لمجلد alembic/versions/، وعدّل down_revision ليطابق
آخر revision عندك (على الأغلب "add_knowledge_variant_id").
"""
from alembic import op
import sqlalchemy as sa

revision = "add_program_group_to_plans"
down_revision = "add_knowledge_variant_id"  # عدّلها لو عندك revision أحدث
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workout_plans", schema=None) as batch_op:
        batch_op.add_column(sa.Column("program_group_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("day_index", sa.Integer(), nullable=True))
        batch_op.create_index("ix_workout_plans_program_group_id", ["program_group_id"])


def downgrade() -> None:
    with op.batch_alter_table("workout_plans", schema=None) as batch_op:
        batch_op.drop_index("ix_workout_plans_program_group_id")
        batch_op.drop_column("day_index")
        batch_op.drop_column("program_group_id")
