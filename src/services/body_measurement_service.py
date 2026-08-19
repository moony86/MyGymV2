from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import and_, desc

from src.infrastructure.db.models import BodyMeasurementTable, TrainingProfileTable


class BodyMeasurementService:
    def __init__(self, db: DbSession):
        self.db = db

    def get_latest(self, profile_id: str) -> Optional[BodyMeasurementTable]:
        return (
            self.db.query(BodyMeasurementTable)
            .filter(BodyMeasurementTable.profile_id == profile_id)
            .order_by(desc(BodyMeasurementTable.date))
            .first()
        )

    def get_history(
        self, profile_id: str, limit: int = 30
    ) -> List[BodyMeasurementTable]:
        return (
            self.db.query(BodyMeasurementTable)
            .filter(BodyMeasurementTable.profile_id == profile_id)
            .order_by(desc(BodyMeasurementTable.date))
            .limit(limit)
            .all()
        )

    def get_by_date(
        self, profile_id: str, target_date: date
    ) -> Optional[BodyMeasurementTable]:
        return (
            self.db.query(BodyMeasurementTable)
            .filter(
                BodyMeasurementTable.profile_id == profile_id,
                BodyMeasurementTable.date == target_date,
            )
            .first()
        )

    def add_measurement(
        self,
        profile_id: str,
        date: date,
        mtype: str,
        goal: Optional[str],
        weight: Optional[Decimal],
        waist: Optional[Decimal],
        narrow_waist: Optional[Decimal],
        chest: Optional[Decimal],
        hips: Optional[Decimal],
        left_arm: Optional[Decimal],
        right_arm: Optional[Decimal],
        left_thigh: Optional[Decimal],
        right_thigh: Optional[Decimal],
        neck: Optional[Decimal],
        body_fat: Optional[Decimal],
        notes: Optional[str],
        conditions: Optional[dict],
        front_photo: Optional[str],
        side_photo: Optional[str],
        back_photo: Optional[str],
    ) -> BodyMeasurementTable:
        existing = self.get_by_date(profile_id, date)
        if existing:
            raise ValueError(
                f"Measurement already exists for {date.isoformat()}"
            )

        measurement = BodyMeasurementTable(
            profile_id=profile_id,
            date=datetime.combine(date, datetime.min.time()),
            type=mtype,
            goal=goal,
            weight=weight,
            waist=waist,
            narrow_waist=narrow_waist,
            chest=chest,
            hips=hips,
            left_arm=left_arm,
            right_arm=right_arm,
            left_thigh=left_thigh,
            right_thigh=right_thigh,
            neck=neck,
            body_fat=body_fat,
            notes=notes,
            conditions=conditions,
            front_photo=front_photo,
            side_photo=side_photo,
            back_photo=back_photo,
        )
        self.db.add(measurement)
        self.db.flush()
        return measurement

    def delete_measurement(self, measurement_id: str, profile_id: str) -> bool:
        measurement = (
            self.db.query(BodyMeasurementTable)
            .filter(
                BodyMeasurementTable.id == measurement_id,
                BodyMeasurementTable.profile_id == profile_id,
            )
            .first()
        )
        if not measurement:
            return False
        self.db.delete(measurement)
        self.db.flush()
        return True