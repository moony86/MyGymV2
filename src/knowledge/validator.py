from __future__ import annotations
from typing import List, Optional
from .models import KnowledgeStore

class KnowledgeValidationError(Exception):
    """خطأ في اتساق البيانات المعرفية"""
    def __init__(self, errors: List[str]):
        super().__init__("\n".join(errors))
        self.errors = errors

class KnowledgeValidator:
    def __init__(self, store: KnowledgeStore):
        self.store = store
        self.errors = []

    def validate(self):
        """تشغيل جميع الفحوصات"""
        self.errors = []

        self._check_referential_integrity()
        self._check_logical_consistency()

        if self.errors:
            raise KnowledgeValidationError(self.errors)
        return True

    def _check_referential_integrity(self):
        # 1. التمارين تشير لأنماط حركة وعضلات موجودة فعلاً
        all_muscle_ids = set(self.store.muscles.keys()) | set(self.store.muscle_groups.keys())

        for ex_id, ex in self.store.exercises.items():
            if ex.movement_pattern not in self.store.movement_patterns:
                self.errors.append(f"Exercise '{ex_id}': Pattern '{ex.movement_pattern}' not found.")

            for m_id in ex.primary_muscles:
                if m_id not in all_muscle_ids:
                    self.errors.append(f"Exercise '{ex_id}': Primary muscle '{m_id}' not found.")

            for m_id in ex.secondary_muscles:
                if m_id not in all_muscle_ids:
                    self.errors.append(f"Exercise '{ex_id}': Secondary muscle '{m_id}' not found.")

        # 2. الـ Variants تشير لتمارين ومعدات موجودة
        for v_id, variant in self.store.variants.items():
            if variant.exercise not in self.store.exercises:
                self.errors.append(f"Variant '{v_id}': Exercise '{variant.exercise}' not found.")

            if variant.equipment not in self.store.equipment:
                self.errors.append(f"Variant '{v_id}': Equipment '{variant.equipment}' not found.")

    def _check_logical_consistency(self):
        # التأكد من أن كل تمرين له على الأقل Variant واحد (اختياري لكن مفيد)
        exercise_ids_in_variants = {v.exercise for v in self.store.variants.values()}
        for ex_id in self.store.exercises:
            if ex_id not in exercise_ids_in_variants:
                # نعتبرها ملاحظة وليس خطأ قاتل (حسب رغبتك)
                print(f"⚠️ Warning: Exercise '{ex_id}' has no variants defined.")

        # فحص قواعد المولد (generator_rules)
        gen_rules = self.store.generator_rules
        # مثال: فحص القوالب المفضلة في القواعد هل هي موجودة في ملف القوالب؟
        for level, config in gen_rules.get("template_selection", {}).items():
            for days, prefs in config.items():
                for t_id in prefs.get("preferred", []):
                    if t_id not in self.store.templates:
                        self.errors.append(f"GeneratorRules: Preferred template '{t_id}' not found in templates.")
