from typing import List
from .training_profile_entity import TrainingProfile
from .enums import ExperienceLevel


class ProfileWarning:
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class ProfileAnalyzer:
    """
    مسؤوليته الوحيدة: تحليل TrainingProfile صحيح بنيويًا وإصدار Warnings
    حول قواعد الأعمال القابلة للتغيير (Business Rules)، دون أي سلطة لمنع
    الحفظ. هذا يفصل صراحة بين:

    - Invariant (في TrainingProfile نفسها): يمنع بناء الكائن أصلًا.
    - Business Rule (هنا): لا تمنع شيئًا، فقط "انتبه / أقترح".

    هذه أول نواة لما سيصبح لاحقًا Rules Engine / Coach.
    """

    def analyze(self, profile: TrainingProfile) -> List[ProfileWarning]:
        warnings: List[ProfileWarning] = []

        if (
            profile.experience_level == ExperienceLevel.BEGINNER
            and profile.training_days_per_week > 6
        ):
            warnings.append(
                ProfileWarning(
                    code="BEGINNER_HIGH_FREQUENCY",
                    message=(
                        "عدد أيام تدريب مرتفع جدًا لمستوى مبتدئ. "
                        "قد يكون من الأفضل البدء بعدد أيام أقل والزيادة تدريجيًا."
                    ),
                )
            )

        if profile.session_duration_minutes < 30 and profile.training_days_per_week >= 5:
            warnings.append(
                ProfileWarning(
                    code="SHORT_SESSION_HIGH_FREQUENCY",
                    message=(
                        "مدة الحصة قصيرة نسبيًا مقارنة بعدد الأيام؛ "
                        "قد يقل الحجم التدريبي الكلي عن المطلوب لتحقيق الهدف."
                    ),
                )
            )

        return warnings
