from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Metadata:
    version: str
    name: str
    description: str


@dataclass(frozen=True)
class WorkoutTemplate:
    id: str
    name: str
    description: str
    category: list[str]
    supported_days: dict[str, int]
    experience: dict[str, bool]
    supports: dict[str, bool]
    recovery_requirement: str
    fatigue_index: int
    complexity_index: int
    weekly_frequency: dict[str, int]
    session_duration: dict[str, int]
    advantages: list[str]
    disadvantages: list[str]
    short_name: str = ""
    rotation_pattern: list[dict[str, Any]] = field(default_factory=list) # 🎯 أضف هذا السطر لكي تدعم الهيكلية الجديدة


@dataclass(frozen=True)
class MuscleGroup:
    id: str
    name: str
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    muscles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Muscle:
    id: str
    name: str
    group: str | None = None
    role: str | None = None
    short_name: str | None = None
    anatomical_name: str | None = None


@dataclass(frozen=True)
class MovementPattern:
    id: str
    name: str
    primary_muscles: list[str]
    secondary_muscles: list[str] = field(default_factory=list)
    movement_type: str | None = None
    description: str | None = None
    category: str | None = None
    exercise_role: str | None = None
    recommended_frequency: dict[str, int] | None = None


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    movement_pattern: str
    primary_muscles: list[str]
    category: str
    secondary_muscles: list[str] = field(default_factory=list)
    exercise_role: str | None = None
    beginner_friendly: bool | None = None
    unilateral: bool | None = None
    estimated_time_minutes: int | None = None


@dataclass(frozen=True)
class ExerciseVariant:
    id: str
    exercise: str
    display_name: str
    equipment: str
    difficulty: str | None = None
    unilateral: bool | None = None
    stability: str | None = None
    machine_required: bool | None = None
    estimated_time_seconds: int | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Equipment:
    id: str
    name: str
    category: str
    beginner_friendly: bool | None = None
    stability: str | None = None
    free_weight: bool | None = None


@dataclass(frozen=True)
class RuleSet:
    id: str
    data: dict[str, Any]


@dataclass
class KnowledgeStore:
    metadata: Metadata | None = None

    templates: dict[str, WorkoutTemplate] = field(default_factory=dict)
    muscle_groups: dict[str, MuscleGroup] = field(default_factory=dict)
    muscles: dict[str, Muscle] = field(default_factory=dict)
    movement_patterns: dict[str, MovementPattern] = field(default_factory=dict)
    exercises: dict[str, Exercise] = field(default_factory=dict)
    variants: dict[str, ExerciseVariant] = field(default_factory=dict)
    equipment: dict[str, Equipment] = field(default_factory=dict)

    training_rules: dict[str, Any] = field(default_factory=dict)
    progression_rules: dict[str, Any] = field(default_factory=dict)
    generator_rules: dict[str, Any] = field(default_factory=dict)
    glossary: dict[str, Any] = field(default_factory=dict)
