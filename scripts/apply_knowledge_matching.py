"""
Apply Knowledge Matching (auto + manual overrides)
====================================================
يطبّق:
1. كل المطابقات التلقائية (score >= 0.85) من match_exercises_to_knowledge.py
2. التصحيحات اليدوية المتفق عليها لفئة "يحتاج مراجعة" و"بدون تطابق"

شغّله مرة وحدة:
    python apply_knowledge_matching.py
"""

from src.apis.deps import get_knowledge_provider
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import ExerciseTable
from match_exercises_to_knowledge import best_match, AUTO_THRESHOLD

# ==========================================================
# التصحيحات اليدوية (راجعناها معًا بناءً على تقرير المطابقة)
# مفتاح: اسم التمرين بالضبط كما هو مخزّن بجدول exercises
# قيمة: variant id الصحيح من القاعدة المعرفية
# ==========================================================
MANUAL_OVERRIDES = {
    "Chest Press (Machine)": "variant.machine_chest_press",
    "Incline Chest Press (Machine)": "variant.machine_incline_press",
    "Preacher Curl (Machine)": "variant.dumbbell_biceps_curl",
    "Triceps Extension (Machine)": "variant.triceps_cable_pushdown",
    "Skull Crusher": "variant.triceps_cable_pushdown",
    "Upper Back Row": "variant.chest_supported_row",
    "Hammer Curl": "variant.dumbbell_biceps_curl",
    # الاقتراح الآلي كان صحيحًا لهذي، بس score أقل من AUTO_THRESHOLD فتجاوزها الكود
    "Bench Press (Barbell)": "variant.barbell_bench_press",
    "Pec Deck Fly": "variant.pec_deck",
    "Overhead Press (Barbell)": "variant.barbell_overhead_press",
    "Lateral Raise": "variant.dumbbell_lateral_raise",
    "Rear Delt Fly": "variant.rear_delt_cable_fly",
    "Squat": "variant.back_squat",
    "Leg Extension": "variant.machine_leg_extension",
    "Leg Curl": "variant.machine_leg_curl",
    "Calf Raise": "variant.standing_calf_raise",
    "Biceps Curl": "variant.dumbbell_biceps_curl",
    "Triceps Pushdown": "variant.triceps_cable_pushdown",
}


def main():
    provider = get_knowledge_provider()
    variants = provider.variants()
    db = SessionLocal()
    exercises = db.query(ExerciseTable).all()

    auto_applied, manual_applied, skipped = 0, 0, []

    for ex in exercises:
        if ex.name in MANUAL_OVERRIDES:
            ex.knowledge_variant_id = MANUAL_OVERRIDES[ex.name]
            manual_applied += 1
            continue

        variant, score = best_match(ex.name, variants)
        if score >= AUTO_THRESHOLD:
            ex.knowledge_variant_id = variant.id
            auto_applied += 1
        else:
            skipped.append(ex.name)

    db.commit()
    db.close()

    print(f"✅ تلقائي: {auto_applied}")
    print(f"✅ تصحيح يدوي: {manual_applied}")
    print(f"⚠️  تم تجاوزها (مو موجودة بـ MANUAL_OVERRIDES ولا score كافي): {skipped}")


if __name__ == "__main__":
    main()
