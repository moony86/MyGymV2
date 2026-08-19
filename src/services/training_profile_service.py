from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session as DbSession

from src.infrastructure.db.models import TrainingProfileTable, DEFAULT_PROFILE_ID
from src.domain.training_profile_entity import TrainingProfile, DEFAULT_PROFILE_ID as DOMAIN_DEFAULT_ID
from src.domain.enums import Sex, ExperienceLevel, TrainingGoal
from src.domain.profile_analyzer import ProfileAnalyzer, ProfileWarning
from typing import List
from src.domain.profile_context import get_current_profile_id


class TrainingProfileService:
    """
    يجيب على سؤال واحد فقط: من هو هذا المتدرب؟

    Input/Output دائمًا TrainingProfile (Domain)، أبدًا TrainingProfileTable.
    كل الـ Business Rules تعيش في TrainingProfile نفسها -- هذا الـ Service
    لا يكرر أي تحقق، فقط ينسّق التحويل من/إلى ORM.

    التطبيق single-user: الوصول دائمًا عبر DEFAULT_PROFILE_ID الثابت،
    لا اعتماد على .first() الضمني.
    """

    def __init__(self, db_session: DbSession, profile_id: Optional[str] = None):
        self.db = db_session
        self.profile_id = profile_id or get_current_profile_id()

    def get_warnings(self, profile: TrainingProfile) -> List[ProfileWarning]:
        """
        تحليل Business Rules بدون أي تأثير على الحفظ. لا تُستدعى تلقائيًا
        داخل create_or_update_profile عمدًا -- الحفظ ينجح دائمًا طالما
        الـ Invariants البنيوية سليمة، بصرف النظر عن هذه التحذيرات.
        """
        return ProfileAnalyzer().analyze(profile)

    def get_profile(self) -> Optional[TrainingProfile]:
        row = self.db.query(TrainingProfileTable).filter(
            TrainingProfileTable.id == self.profile_id
        ).first()
        if row is None:
            return None
        return self._to_domain(row)

    def create_or_update_profile(
        self,
        sex: str,
        birth_year: int,
        height_cm: Decimal,
        current_weight_kg: Decimal,
        experience_level: str,
        training_days_per_week: int,
        session_duration_minutes: int,
        primary_goal: str,
    ) -> TrainingProfile:
        # كل التحقق يحدث هنا فعليًا، عبر بناء الـ Domain Entity نفسه.
        # لو القيم غير صالحة، Pydantic يرفع ValueError قبل ما نلمس الـ DB إطلاقًا.
        profile = TrainingProfile(
            sex=Sex(sex),
            birth_year=birth_year,
            height_cm=height_cm,
            current_weight_kg=current_weight_kg,
            experience_level=ExperienceLevel(experience_level),
            training_days_per_week=training_days_per_week,
            session_duration_minutes=session_duration_minutes,
            primary_goal=TrainingGoal(primary_goal),
        )
        return self._save(profile)

    def update_weight(self, current_weight_kg: Decimal) -> TrainingProfile:
        """
        نقطة التوسعة المستقبلية لـ WeightHistory -- بدون تغيير هذا التوقيع.
        """
        current = self.get_profile()
        if current is None:
            raise ValueError("No training profile exists yet.")

        data = current.model_dump()
        data["current_weight_kg"] = current_weight_kg
        updated = TrainingProfile(**data)
        return self._save(updated)

    # ---------- تحويل Domain <-> ORM ----------

    def _save(self, profile: TrainingProfile) -> TrainingProfile:
        row = self.db.query(TrainingProfileTable).filter(
            TrainingProfileTable.id == self.profile_id
        ).first()
        if row is None:
            row = TrainingProfileTable(id=self.profile_id)
            self.db.add(row)

        row.sex = profile.sex.value
        row.birth_year = profile.birth_year
        row.height_cm = profile.height_cm
        row.current_weight_kg = profile.current_weight_kg
        row.experience_level = profile.experience_level.value
        row.training_days_per_week = profile.training_days_per_week
        row.session_duration_minutes = profile.session_duration_minutes
        row.primary_goal = profile.primary_goal.value

        self.db.flush()
        return self._to_domain(row)

    def _to_domain(self, row: TrainingProfileTable) -> TrainingProfile:
        return TrainingProfile(
            id=row.id,
            sex=Sex(row.sex),
            birth_year=row.birth_year,
            height_cm=Decimal(str(row.height_cm)),
            current_weight_kg=Decimal(str(row.current_weight_kg)),
            experience_level=ExperienceLevel(row.experience_level),
            training_days_per_week=row.training_days_per_week,
            session_duration_minutes=row.session_duration_minutes,
            primary_goal=TrainingGoal(row.primary_goal),
            updated_at=row.updated_at,
        )
