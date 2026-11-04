"""
Seed Exercises Table from Knowledge Base (YAML)
==============================================
يقوم بتغذية وتحديث جدول exercises في قاعدة البيانات بجميع الـ Variants
الموجودة في ملفات YAML تلقائياً مع حل تعارض الأسماء المكررة.

طريقة الاستخدام:
    python scripts/seed_exercises.py
"""

import sys
from pathlib import Path
from uuid6 import uuid7

# إضافة مسار المشروع الأساسي
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.apis.deps import get_knowledge_provider
from src.infrastructure.db.connection import SessionLocal, engine
from src.infrastructure.db.models import Base, ExerciseTable


def seed_database():
    # إنشاء الجداول إذا لم تكن موجودة
    Base.metadata.create_all(bind=engine)

    provider = get_knowledge_provider()
    variants = provider.variants()
    exercises_map = {ex.id: ex for ex in provider.exercises()}

    db = SessionLocal()
    try:
        # قراءة التمارين الموجودة مسبقاً
        existing_by_variant = {
            row.knowledge_variant_id: row
            for row in db.query(ExerciseTable).filter(ExerciseTable.knowledge_variant_id.isnot(None)).all()
        }

        existing_by_name = {row.name: row for row in db.query(ExerciseTable).all()}

        added, updated = 0, 0
        used_names = set(existing_by_name.keys())

        for variant in variants:
            parent_exercise = exercises_map.get(variant.exercise)
            primary_muscle = (
                parent_exercise.primary_muscles[0]
                if parent_exercise and parent_exercise.primary_muscles
                else "unknown"
            )

            # معالجة تفادي تكرار الاسم في قاعدة البيانات (Unique Name Constraint)
            target_name = variant.display_name

            # 1. إذا كان الـ Variant ينتمي لصف موجود أصلاً بـ Variant ID
            if variant.id in existing_by_variant:
                db_row = existing_by_variant[variant.id]
                db_row.equipment = variant.equipment.replace("equipment.", "")
                db_row.difficulty = variant.difficulty or "intermediate"
                updated += 1

            # 2. إذا كان ينتمي لتمرين قديم بنفس الاسم
            elif target_name in existing_by_name:
                db_row = existing_by_name[target_name]
                db_row.knowledge_variant_id = variant.id
                db_row.equipment = variant.equipment.replace("equipment.", "")
                db_row.difficulty = variant.difficulty or "intermediate"
                updated += 1

            # 3. إذا كان تمرين جديد
            else:
                # التأكد من أن الاسم فريد وغير مكرر
                if target_name in used_names:
                    # إضافة تمييز بسيط بالمعُدة لتجنب التكرار
                    equip_short = variant.equipment.replace("equipment.", "").title()
                    target_name = f"{variant.display_name} ({equip_short})"

                new_exercise = ExerciseTable(
                    id=str(uuid7()),
                    name=target_name,
                    primary_muscle=primary_muscle.replace("muscle.", ""),
                    equipment=variant.equipment.replace("equipment.", ""),
                    difficulty=variant.difficulty or "intermediate",
                    is_active=True,
                    knowledge_variant_id=variant.id,
                )
                db.add(new_exercise)
                used_names.add(target_name)
                added += 1

        db.commit()
        print(f"✅ تم زرع البيانات بنجاح! الإضافة: {added} تمرين جديد، التحديث/الربط: {updated} تمرين.")

    except Exception as e:
        db.rollback()
        print(f"❌ فشل عملية الـ Seed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
