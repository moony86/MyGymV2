"""
Knowledge Consistency Checker
=============================
يتحقق من أن كل ID مُشار إليه بأي ملف YAML موجود فعليًا بمكانه الأصلي،
وأنه ما فيه تكرار لنفس الـ ID. لا يتحقق من "جودة" القواعد، فقط من
اتساق الإشارات المرجعية (Referential Integrity) بين الملفات.

الاستخدام:
    python knowledge_checker.py /path/to/knowledge/
"""
import sys
import yaml
from pathlib import Path
from collections import defaultdict


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_ids(items, key="id"):
    return {item[key] for item in items if key in item}


def check(knowledge_dir: Path):
    errors = []
    warnings = []

    # ---------- تحميل كل الملفات ----------
    templates = load_yaml(knowledge_dir / "templates.yaml")["templates"]
    muscles_data = load_yaml(knowledge_dir / "muscles.yaml")
    movement_patterns = load_yaml(knowledge_dir / "movement_patterns.yaml")["movement_patterns"]
    exercises = load_yaml(knowledge_dir / "exercises.yaml")["exercises"]
    variants = load_yaml(knowledge_dir / "exercise_variants.yaml")["variants"]
    equipment = load_yaml(knowledge_dir / "equipment.yaml")["equipment"]
    generator_rules = load_yaml(knowledge_dir / "generator_rules.yaml")
    training_rules = load_yaml(knowledge_dir / "training_rules.yaml")

    # ---------- بناء سجلات الـ IDs ----------
    template_ids = collect_ids(templates)
    movement_ids = collect_ids(movement_patterns)
    exercise_ids = collect_ids(exercises)
    variant_ids = collect_ids(variants)
    equipment_ids = collect_ids(equipment)

    muscle_group_ids = collect_ids(muscles_data.get("muscle_groups", []))
    muscle_ids = collect_ids(muscles_data.get("muscles", []))
    all_muscle_ids = muscle_group_ids | muscle_ids  # بعض الملفات تشير لمجموعة، وبعضها لعضلة محددة

    # ---------- 1) تكرار الـ IDs داخل كل فئة ----------
    def check_duplicates(items, label):
        seen = defaultdict(int)
        for item in items:
            if "id" in item:
                seen[item["id"]] += 1
        for id_, count in seen.items():
            if count > 1:
                errors.append(f"[DUPLICATE] {label}: '{id_}' مكرر {count} مرات")

    check_duplicates(templates, "templates.yaml")
    check_duplicates(movement_patterns, "movement_patterns.yaml")
    check_duplicates(exercises, "exercises.yaml")
    check_duplicates(variants, "exercise_variants.yaml")
    check_duplicates(equipment, "equipment.yaml")

    # ---------- 2) exercises.yaml: التحقق من movement_pattern + muscles ----------
    for ex in exercises:
        eid = ex.get("id", "UNKNOWN")
        mp = ex.get("movement_pattern")
        if mp and mp not in movement_ids:
            errors.append(f"[exercises.yaml] '{eid}' يشير لـ movement_pattern غير موجود: '{mp}'")

        for m in ex.get("primary_muscles", []) or []:
            if m not in all_muscle_ids:
                errors.append(f"[exercises.yaml] '{eid}' يشير لعضلة غير موجودة (primary): '{m}'")
        for m in ex.get("secondary_muscles", []) or []:
            if m not in all_muscle_ids:
                errors.append(f"[exercises.yaml] '{eid}' يشير لعضلة غير موجودة (secondary): '{m}'")

    # ---------- 3) exercise_variants.yaml: التحقق من exercise + equipment ----------
    exercises_with_variants = set()
    for v in variants:
        vid = v.get("id", "UNKNOWN")
        ex_ref = v.get("exercise")
        eq_ref = v.get("equipment")
        if ex_ref and ex_ref not in exercise_ids:
            errors.append(f"[exercise_variants.yaml] '{vid}' يشير لتمرين غير موجود: '{ex_ref}'")
        else:
            exercises_with_variants.add(ex_ref)
        if eq_ref and eq_ref not in equipment_ids:
            errors.append(f"[exercise_variants.yaml] '{vid}' يشير لمعدّة غير موجودة: '{eq_ref}'")

    for eid in exercise_ids - exercises_with_variants:
        warnings.append(f"[coverage] التمرين '{eid}' ما له أي variant معرّف بعد (مو خطأ، بس نقص)")

    # ---------- 4) movement_patterns.yaml: التحقق من العضلات ----------
    for mp in movement_patterns:
        mid = mp.get("id", "UNKNOWN")
        for m in mp.get("primary_muscles", []) or []:
            if m not in all_muscle_ids:
                errors.append(f"[movement_patterns.yaml] '{mid}' يشير لعضلة غير موجودة (primary): '{m}'")
        for m in mp.get("secondary_muscles", []) or []:
            if m not in all_muscle_ids:
                errors.append(f"[movement_patterns.yaml] '{mid}' يشير لعضلة غير موجودة (secondary): '{m}'")

    # ---------- 5) generator_rules.yaml ----------
    tmpl_sel = generator_rules.get("template_selection", {})
    for level, days_map in tmpl_sel.items():
        for days_key, pref in days_map.items():
            for tid in pref.get("preferred", []) or []:
                if tid not in template_ids:
                    errors.append(
                        f"[generator_rules.yaml] template_selection.{level}.{days_key} "
                        f"يشير لقالب غير موجود: '{tid}'"
                    )

    for mv in generator_rules.get("movement_selection", {}).get("required", []) or []:
        if mv not in movement_ids:
            errors.append(f"[generator_rules.yaml] movement_selection.required يشير لحركة غير موجودة: '{mv}'")

    variant_sel = generator_rules.get("variant_selection", {})
    for level, rules in variant_sel.items():
        for key in ("prefer", "avoid"):
            for eq in rules.get(key, []) or []:
                if eq not in equipment_ids:
                    errors.append(
                        f"[generator_rules.yaml] variant_selection.{level}.{key} "
                        f"يشير لمعدّة غير موجودة: '{eq}'"
                    )

    # ---------- 6) training_rules.yaml ----------
    mv_coverage = training_rules.get("movement_coverage", {})
    for key in ("required", "optional"):
        for mv in mv_coverage.get(key, []) or []:
            if mv not in movement_ids:
                errors.append(f"[training_rules.yaml] movement_coverage.{key} يشير لحركة غير موجودة: '{mv}'")

    m_coverage = training_rules.get("muscle_coverage", {})
    for key in ("major_muscles", "optional_muscles"):
        for m in m_coverage.get(key, []) or []:
            if m not in all_muscle_ids:
                errors.append(f"[training_rules.yaml] muscle_coverage.{key} يشير لعضلة/مجموعة غير موجودة: '{m}'")

    return errors, warnings


if __name__ == "__main__":
    knowledge_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("knowledge")
    errors, warnings = check(knowledge_path)

    print(f"فحص {knowledge_path} ...\n")

    if errors:
        print(f"❌ {len(errors)} خطأ (لازم يُصلح قبل أي كود Generator):\n")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ صفر أخطاء إشارات مرجعية.")

    print()
    if warnings:
        print(f"⚠️  {len(warnings)} ملاحظة (معلومات، مو أخطاء):\n")
        for w in warnings:
            print(f"  - {w}")

    sys.exit(1 if errors else 0)
