from enum import Enum

class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"

class SetType(str, Enum):
    WARMUP = "warmup"
    WORKING = "working"
    DROPSET = "dropset"
    FAILURE = "failure"
    AMRAP = "amrap"  # إضافي للمستقبل

class Sex(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class ExperienceLevel(str, Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class TrainingGoal(str, Enum):
    HYPERTROPHY = "HYPERTROPHY"
    STRENGTH = "STRENGTH"
    FAT_LOSS = "FAT_LOSS"
    GENERAL_FITNESS = "GENERAL_FITNESS"
