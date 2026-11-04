from __future__ import annotations

from .models import (
    Exercise,
    ExerciseVariant,
    KnowledgeStore,
    MovementPattern,
    Muscle,
    WorkoutTemplate,
    Equipment,
)


class KnowledgeProvider:
    """
    Read-only interface over the loaded knowledge base.

    Every part of the application should use this class
    instead of reading YAML directly.
    """

    def __init__(self, store: KnowledgeStore):

        self._store = store

    # =====================================================
    # Templates
    # =====================================================

    def templates(self) -> list[WorkoutTemplate]:
        return list(self._store.templates.values())

    def template(self, template_id: str) -> WorkoutTemplate:

        return self._store.templates[template_id]

    # =====================================================
    # Muscles
    # =====================================================

    def muscles(self) -> list[Muscle]:

        return list(self._store.muscles.values())

    def muscle(self, muscle_id: str) -> Muscle:

        return self._store.muscles[muscle_id]

    # =====================================================
    # Movement Patterns
    # =====================================================

    def movement_patterns(self) -> list[MovementPattern]:

        return list(self._store.movement_patterns.values())

    def movement_pattern(
        self,
        pattern_id: str,
    ) -> MovementPattern:

        return self._store.movement_patterns[pattern_id]

    # =====================================================
    # Exercises
    # =====================================================

    def exercises(self) -> list[Exercise]:

        return list(self._store.exercises.values())

    def exercise(self, exercise_id: str) -> Exercise:

        return self._store.exercises[exercise_id]

    # =====================================================
    # Variants
    # =====================================================

    def variants(self) -> list[ExerciseVariant]:

        return list(self._store.variants.values())

    def variant(
        self,
        variant_id: str,
    ) -> ExerciseVariant:

        return self._store.variants[variant_id]

    # =====================================================
    # Equipment
    # =====================================================

    def equipment(self) -> list[Equipment]:

        return list(self._store.equipment.values())

    def equipment_item(
        self,
        equipment_id: str,
    ) -> Equipment:

        return self._store.equipment[equipment_id]

    # =====================================================
    # Rules
    # =====================================================

    @property
    def training_rules(self):

        return self._store.training_rules

    @property
    def progression_rules(self):

        return self._store.progression_rules

    @property
    def generator_rules(self):

        return self._store.generator_rules

    @property
    def glossary(self):

        return self._store.glossary
