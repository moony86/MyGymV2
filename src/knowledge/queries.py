from __future__ import annotations
from typing import List, Optional
from .provider import KnowledgeProvider
from .models import Exercise, ExerciseVariant, WorkoutTemplate

class KnowledgeQueries:
    def __init__(self, provider: KnowledgeProvider):
        self.provider = provider

    def get_exercises_by_muscle(self, muscle_id: str) -> List[Exercise]:
        return [ex for ex in self.provider.exercises() if muscle_id in ex.primary_muscles]

    def get_variants_for_exercise(self, exercise_id: str, equipment_ids: List[str] = None) -> List[ExerciseVariant]:
        variants = [v for v in self.provider.variants() if v.exercise == exercise_id]
        if equipment_ids:
            variants = [v for v in variants if v.equipment in equipment_ids]
        return variants

    def get_templates_for_days(self, days: int) -> List[WorkoutTemplate]:
        return [
            t for t in self.provider.templates()
            if t.supported_days["minimum"] <= days <= t.supported_days["maximum"]
        ]
