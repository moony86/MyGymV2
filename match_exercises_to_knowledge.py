"""
Match Exercises to Knowledge Base
==================================
يطابق كل صف بجدول exercises (القديم) مع أقرب exercise_variant
بالقاعدة المعرفية، عن طريق تشابه الاسم (display_name / aliases).

طريقة الاستخدام:
    python match_exercises_to_knowledge.py            # وضع المعاينة فقط (dry-run)
    python match_exercises_to_knowledge.py --apply     # يطبّق فعليًا على قاعدة البيانات

المخرجات:
    - "auto_matched": تشابه >= 0.85، يُطبّق تلقائيًا مع --apply
    - "needs_review": تشابه بين 0.5 و 0.85، يحتاج مراجعتك اليدوية
    - "no_match": ما فيه أي تشابه معقول، يبقى knowledge_variant_id فارغ
"""

import argparse
import difflib
import sys
from pathlib import Path

# عدّل هذا المسار حسب موقع المشروع الفعلي
sys.path.insert(0, str(Path(__file__).parent))

from src.apis.deps import get_knowledge_provider
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import ExerciseTable

AUTO_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.50


def normalize(text: str) -> str:
    return text.lower().strip().replace("-", " ").replace("_", " ")


def best_match(exercise_name: str, variants: list) -> tuple[dict | None, float]:
    """يرجّع (أفضل variant، درجة التشابه) بمقارنة الاسم مع display_name وكل alias."""
    target = normalize(exercise_name)
    best_variant, best_score = None, 0.0

    for variant in variants:
        candidates = [variant.display_name] + list(variant.aliases or [])
        for candidate in candidates:
            score = difflib.SequenceMatcher(None, target, normalize(candidate)).ratio()
            if score > best_score:
                best_score, best_variant = score, variant

    return best_variant, best_score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="طبّق التغييرات فعليًا على قاعدة البيانات")
    args = parser.parse_args()

    provider = get_knowledge_provider()
    variants = provider.variants()

    db = SessionLocal()
    exercises = db.query(ExerciseTable).all()

    auto_matched, needs_review, no_match = [], [], []

    for ex in exercises:
        variant, score = best_match(ex.name, variants)
        row = {"exercise_id": ex.id, "exercise_name": ex.name,
               "variant_id": variant.id if variant else None,
               "variant_name": variant.display_name if variant else None,
               "score": round(score, 2)}

        if score >= AUTO_THRESHOLD:
            auto_matched.append(row)
        elif score >= REVIEW_THRESHOLD:
            needs_review.append(row)
        else:
            no_match.append(row)

    # ---- التقرير ----
    print(f"\n✅ مطابقة تلقائية ({len(auto_matched)}):")
    for r in auto_matched:
        print(f"   {r['exercise_name']!r:40} -> {r['variant_name']} (score={r['score']})")

    print(f"\n⚠️  يحتاج مراجعة يدوية ({len(needs_review)}):")
    for r in needs_review:
        print(f"   {r['exercise_name']!r:40} -> {r['variant_name']} (score={r['score']})")

    print(f"\n❌ بدون تطابق ({len(no_match)}):")
    for r in no_match:
        print(f"   {r['exercise_name']!r:40} -> بيبقى بدون ربط، تقدر تربطه يدويًا لاحقًا")

    if not args.apply:
        print("\n(وضع معاينة فقط — شغّل بـ --apply لتطبيق المطابقة التلقائية فعليًا)")
        db.close()
        return

    # ---- التطبيق (فقط auto_matched، النوعين الثانيين يحتاجون قرار بشري) ----
    applied = 0
    for r in auto_matched:
        ex = db.query(ExerciseTable).filter(ExerciseTable.id == r["exercise_id"]).first()
        ex.knowledge_variant_id = r["variant_id"]
        applied += 1
    db.commit()
    print(f"\n💾 تم تطبيق الربط على {applied} صف (المطابقة التلقائية فقط).")
    print("راجع قائمة needs_review وطبّقها يدويًا عبر UPDATE مباشر أو عدّل الحد الأدنى.")
    db.close()


if __name__ == "__main__":
    main()
