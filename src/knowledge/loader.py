from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Type, TypeVar

import yaml

from .models import (
    Equipment,
    Exercise,
    ExerciseVariant,
    KnowledgeStore,
    MovementPattern,
    Muscle,
    MuscleGroup,
    WorkoutTemplate,
)

T = TypeVar("T")

class KnowledgeLoader:
    """
    محمل ذكي يقوم بتحويل ملفات YAML إلى كائنات برمجية مع فلترة الحقول الزائدة
    لضمان عدم انهيار البرنامج عند اختلاف هيكلية البيانات.
    """

    REQUIRED_FILES = {
        "templates": "templates.yaml",
        "muscles": "muscles.yaml",
        "movement_patterns": "movement_patterns.yaml",
        "exercises": "exercises.yaml",
        "exercise_variants": "exercise_variants.yaml",
        "equipment": "equipment.yaml",
        "training_rules": "training_rules.yaml",
        "progression_rules": "program_progression_rules.yaml",
        "generator_rules": "generator_rules.yaml",
        "glossary": "glossary.yaml",
    }

    def __init__(self, knowledge_path: str | Path):
        self.root = Path(knowledge_path)
        if not self.root.exists():
            raise FileNotFoundError(f"Knowledge folder not found: {self.root}")

    # ======================================================
    # PRIVATE HELPERS
    # ======================================================

    def _safe_instantiate(self, cls: Type[T], data: dict[str, Any]) -> T:
        """
        تأخذ البيانات وتمرر للكلاس فقط الحقول التي يتوقعها في الـ __init__.
        هذا يمنع خطأ TypeError: unexpected keyword argument.
        """
        # الحصول على قائمة البارامترات التي يقبلها الكلاس
        signature = inspect.signature(cls)
        cls_params = signature.parameters.keys()

        # فلترة القاموس ليحتوي فقط على المفاتيح الموجودة في الكلاس
        filtered_data = {k: v for k, v in data.items() if k in cls_params}
        return cls(**filtered_data)

    def _load_yaml(self, key: str) -> Any:
        filename = self.REQUIRED_FILES[key]
        path = self.root / filename

        if not path.exists():
            raise FileNotFoundError(f"Missing required knowledge file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"File {filename} is empty or invalid.")
        return data

    def _load_collection(self, key: str, model_cls: Type[T], plural_key: str = None) -> dict[str, T]:
        """دالة عامة لتحميل القوائم وتحويلها لقاموس يعتمد على الـ ID"""
        plural_key = plural_key or key
        raw = self._load_yaml(key)

        return {
            item["id"]: self._safe_instantiate(model_cls, item)
            for item in raw[plural_key]
        }

    # ======================================================
    # PUBLIC LOAD METHOD
    # ======================================================

    def load(self) -> KnowledgeStore:
        store = KnowledgeStore()

        # تحميل الكائنات الأساسية باستخدام المحمل الذكي
        store.templates = self._load_collection("templates", WorkoutTemplate)
        store.muscle_groups = self._load_collection("muscles", MuscleGroup, "muscle_groups")
        store.muscles = self._load_collection("muscles", Muscle, "muscles")
        store.movement_patterns = self._load_collection("movement_patterns", MovementPattern)
        store.exercises = self._load_collection("exercises", Exercise)

        # لاحظ أن مفاتيح الـ YAML لهذه الملفات تختلف (variants, equipment)
        store.variants = self._load_collection("exercise_variants", ExerciseVariant, "variants")
        store.equipment = self._load_collection("equipment", Equipment, "equipment")

        # تحميل القواعد العامة كقواميس (Dictionaries) لأنها متغيرة الهيكل
        store.training_rules = self._load_yaml("training_rules")
        store.progression_rules = self._load_yaml("progression_rules")
        store.generator_rules = self._load_yaml("generator_rules")
        store.glossary = self._load_yaml("glossary")

        return store
