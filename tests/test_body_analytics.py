from datetime import datetime,timezone,timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.infrastructure.db.models import Base,ProfileTable,BodyMeasurementTable
from src.queries import body_analytics as q

@pytest.fixture
def db(monkeypatch):
    e=create_engine('sqlite:///:memory:');Base.metadata.create_all(e)
    monkeypatch.setattr(q,'_now',lambda:datetime(2026,10,27,12,tzinfo=timezone.utc))
    with Session(e) as db:
        db.add_all([ProfileTable(id='a',name='A'),ProfileTable(id='b',name='B')]);db.commit();yield db
    e.dispose()

def record(db,date,owner='a',created=None,**fields):
    db.add(BodyMeasurementTable(id=str(uuid.uuid4()),profile_id=owner,date=datetime.fromisoformat(date),created_at=created or datetime(2026,10,27,10),type='weekly',**fields));db.commit()

def test_changes_use_per_field_dates_and_percentage_points(db):
    record(db,'2026-10-19',weight=Decimal('80.5'),body_fat=Decimal('20'))
    record(db,'2026-10-23',waist=Decimal('90'))
    record(db,'2026-10-27',weight=Decimal('79.5'),body_fat=Decimal('18'),waist=Decimal('88'))
    f=q.body_report(db,'a',8)['fields']
    assert f['weight']['change']==-1 and f['weight']['span_days']==8
    assert f['waist']['change']==-2 and f['waist']['span_days']==4
    assert f['body_fat']['change']==-2 and f['body_fat']['change_unit']=='percentage_points'

def test_one_value_is_not_zero_change_and_profiles_are_separate(db):
    record(db,'2026-10-27',weight=Decimal('80'))
    record(db,'2026-10-27',owner='b',weight=Decimal('40'))
    report=q.body_report(db,'a');assert report['recorded_days']==1
    assert report['fields']['weight']['latest']['value']==80
    assert report['fields']['weight']['change'] is None

def test_period_and_future_dates_are_enforced(db):
    record(db,'2026-10-19',weight=Decimal('90'))
    record(db,'2026-10-27',weight=Decimal('80'))
    record(db,'2026-10-28',weight=Decimal('60'))
    assert q.body_report(db,'a',1)['fields']['weight']['change'] is None
    assert q.body_report(db,'a',4)['fields']['weight']['change']==-10

def test_legacy_duplicate_day_uses_latest_entry_without_extra_trend_points(db):
    record(db,'2026-10-27',created=datetime(2026,10,27,8),weight=Decimal('79'))
    record(db,'2026-10-27',created=datetime(2026,10,27,9),weight=Decimal('80'))
    r=q.body_report(db,'a');assert r['legacy_duplicate_days']==1
    assert r['fields']['weight']['latest']['value']==80
    assert r['fields']['weight']['observations']==1
