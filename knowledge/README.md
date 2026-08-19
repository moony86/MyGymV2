# Gym Knowledge Engine

## Overview

Gym Knowledge Engine is a domain knowledge base designed to power a rule-based workout planning system.

It does not generate workout plans directly.

Instead, it provides structured knowledge that other modules use for:

- Workout Generation
- Workout Evaluation
- Performance Analysis
- Exercise Recommendation
- Exercise Replacement
- Future AI Integration (Optional)

The goal is to separate domain knowledge from application logic.

---

# Design Philosophy

The system follows one simple principle:

> Code should contain algorithms.
>
> Knowledge should contain facts.

Example:

Bad

if user.training_days <= 3:
    use Full Body

Good

Generator asks the Knowledge Base:

"What templates support 3 training days?"

The knowledge base returns:

- Full Body

The Generator decides.

---

# Architecture

knowledge/

├── README.md
├── glossary.yaml
├── templates.yaml
├── muscles.yaml
├── movement_patterns.yaml
├── exercises.yaml
├── exercise_variants.yaml
├── equipment.yaml
├── training_rules.yaml
├── progression_rules.yaml
└── generator_rules.yaml

---

# Responsibilities

README.md

Project philosophy.

glossary.yaml

Defines every domain term used in the project.

templates.yaml

Workout templates.

Example:

- Full Body
- Upper Lower
- Push Pull Legs

muscles.yaml

Defines the body hierarchy.

movement_patterns.yaml

Defines movement patterns.

Examples:

- Horizontal Push
- Horizontal Pull
- Vertical Push
- Hip Hinge

exercises.yaml

Defines abstract exercises.

Example:

Horizontal Press

NOT

Bench Press

exercise_variants.yaml

Stores implementation variants.

Example:

Horizontal Press

↓

Machine

↓

Barbell

↓

Dumbbell

equipment.yaml

Gym equipment database.

training_rules.yaml

Scientific rules used by every module.

progression_rules.yaml

Rules for progressive overload.

generator_rules.yaml

Decision rules used by Workout Generator.

---

# Rule Engine

Knowledge never executes.

Generator reads knowledge.

Example

User

↓

Generator

↓

Knowledge Base

↓

Decision

---

# IDs

Every entity must have a permanent id.

Example

template.full_body

exercise.horizontal_press

muscle.chest.upper

movement.horizontal_push

Equipment.machine.chest_press

IDs are immutable.

Names can change.

IDs never change.

---

# Naming Convention

IDs

snake_case

Files

snake_case

Properties

snake_case

No spaces.

---

# Relationships

Everything references IDs.

Never names.

Correct

primary_muscles:

- muscle.chest.middle

Wrong

primary_muscles:

- Chest

---

# Project Scope

Target users

✓ Beginners

✓ Returning trainees

✓ Busy people

Not intended for

✗ Competitive Bodybuilders

✗ Elite Powerlifters

✗ Professional Coaches

---

# Goal

Generate simple, safe and effective workout programs based on evidence-based training principles while remaining fully explainable.

No hidden AI decisions.

Every recommendation must be traceable back to explicit knowledge.
