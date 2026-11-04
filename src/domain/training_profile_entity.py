import uuid
import uuid6
from decimal import Decimal
from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .enums import Sex, ExperienceLevel, TrainingGoal  # بعد دمج training_enums_addition.py هنا

# التطبيق single-user حاليًا: هوية ثابتة ومعروفة للصف الوحيد.
# هذا يمنع نهائيًا الاعتماد الضمني على أول صف (.first()).
DEFAULT_PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TrainingProfile(BaseModel):
    """
    يجيب على سؤال واحد: من هو هذا المتدرب؟
    هذا هو المصدر الوحيد للـ Business Rules الخاصة بالبروفايل.
    Service لا يكرر أي تحقق موجود هنا.
    """
    id: uuid.UUID = Field(default_factory=lambda: DEFAULT_PROFILE_ID)
    sex: Sex
    birth_year: int
    height_cm: Decimal
    current_weight_kg: Decimal
    experience_level: ExperienceLevel
    training_days_per_week: int
    session_duration_minutes: int
    primary_goal: TrainingGoal
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=False)

    # ---------- Validators (Business Rules) ----------

    @field_validator("birth_year")
    @classmethod
    def validate_birth_year(cls, v: int) -> int:
        current_year = date.today().year
        # 14-90 سنة تقريبًا هو المدى الواقعي لمستخدم التطبيق
        if not (current_year - 90 <= v <= current_year - 14):
            raise ValueError("birth_year يعطي عمرًا خارج المدى الواقعي (14-90 سنة).")
        return v

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v: Decimal) -> Decimal:
        if not (Decimal("100") <= v <= Decimal("250")):
            raise ValueError("height_cm out of realistic range.")
        return v

    @field_validator("current_weight_kg")
    @classmethod
    def validate_weight(cls, v: Decimal) -> Decimal:
        if not (Decimal("30") <= v <= Decimal("300")):
            raise ValueError("current_weight_kg out of realistic range.")
        return v

    @field_validator("training_days_per_week")
    @classmethod
    def validate_days(cls, v: int) -> int:
        if not (1 <= v <= 7):
            raise ValueError("training_days_per_week must be between 1 and 7.")
        return v

    @field_validator("session_duration_minutes")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if not (15 <= v <= 240):
            raise ValueError("session_duration_minutes out of realistic range.")
        return v

    # ملاحظة: قاعدة "مبتدئ + أيام كثيرة جدًا" ليست Invariant بنيويًا، بل
    # Business Rule قابلة للتغيير مستقبلًا (راجع ProfileAnalyzer). لا تُمنع
    # هنا، فقط تُرصد كـ Warning غير مانع للحفظ.

    # ---------- خصائص مشتقة (لا تُخزَّن) ----------

    @property
    def age(self) -> int:
        """العمر يُحسب دائمًا وقت الحاجة، لا يُخزَّن أبدًا."""
        return date.today().year - self.birth_year
