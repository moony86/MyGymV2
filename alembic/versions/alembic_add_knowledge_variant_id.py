"""add knowledge_variant_id to exercises

هذا migration يضيف عمود ربط اختياري (nullable) بين جدول exercises
الحالي وبين exercise_variants.yaml بالقاعدة المعرفية.
لا يحذف ولا يعدّل أي عمود أو صف موجود — إضافة بحتة، آمنة 100%.

انسخ هذا الملف داخل مجلد alembic/versions/ عندك، وعدّل down_revision
ليطابق آخر revision موجود عندك حاليًا.
"""
from alembic import op
import sqlalchemy as sa

revision = "add_knowledge_variant_id"
down_revision = "9766ac66abfe"  # الـ initial_schema اللي رفعته
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite يحتاج batch mode حتى لإضافة عمود بسيط (نفس أسلوب باقي ملفاتك)
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("knowledge_variant_id", sa.String(150), nullable=True)
        )
        batch_op.create_index(
            "ix_exercises_knowledge_variant_id", ["knowledge_variant_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.drop_index("ix_exercises_knowledge_variant_id")
        batch_op.drop_column("knowledge_variant_id")
