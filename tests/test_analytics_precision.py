from datetime import datetime,timedelta,timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.infrastructure.db.models import Base,ProfileTable,ExerciseTable,SessionTable,PerformedExerciseTable,SetTable
from src.queries import analytics_queries as q
NOW=datetime(2026,10,26,12,tzinfo=timezone.utc)

@pytest.fixture
def db(monkeypatch):
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    monkeypatch.setattr(q,'_now',lambda:NOW)
    with Session(engine) as db:
        db.add_all([ProfileTable(id='a',name='A'),ProfileTable(id='b',name='B')]);db.commit();yield db
    engine.dispose()

def record(db,days=0,owner='a',weight='20',reps=8,rpe=None,rir=None,status='COMPLETED',kind='working',name='Bench',equipment='barbell',at=None):
    exercise=db.query(ExerciseTable).filter_by(name=name).first()
    if not exercise:
        exercise=ExerciseTable(id=str(uuid.uuid4()),name=name,primary_muscle='chest',equipment=equipment,is_active=True);db.add(exercise);db.flush()
    sid=str(uuid.uuid4());pid=str(uuid.uuid4())
    date=(at or NOW-timedelta(days=days,minutes=1)).replace(tzinfo=None)
    db.add(SessionTable(id=sid,profile_id=owner,status=status,started_at=date,ended_at=date+timedelta(seconds=30)));db.flush()
    db.add(PerformedExerciseTable(id=pid,session_id=sid,exercise_id=exercise.id,display_order=0));db.flush()
    db.add(SetTable(id=str(uuid.uuid4()),performed_exercise_id=pid,set_order=1,weight=Decimal(weight),reps=reps,rpe=rpe,rir=rir,set_type=kind));db.commit()
    return exercise.id

def test_empty_is_not_healthy_or_zero_strength(db):
    assert q.get_data_quality(db,'a')['total_sets']==0
    assert q.get_actionable_insights(db,'a')[0]['code']=='no_data'
    assert q.get_exercise_prs(db,'a','missing')['best_e1rm'] is None

def test_first_session_does_not_become_one_eighth_week(db):
    record(db)
    m=q.get_muscle_balance(db,'a',8)
    assert m['muscles'][0]['total_sets']==1
    assert m['muscles'][0]['current_week_sets']==1
    assert m['muscles'][0]['weekly_sets'] is None
    assert m['completed_observed_weeks']==0

def test_complete_weeks_include_missing_logs_but_exclude_pretracking(db):
    record(db,days=14);record(db,days=13)
    m=q.get_muscle_balance(db,'a',8)
    assert m['completed_observed_weeks']==2
    assert m['muscles'][0]['weekly_sets']==1
    trends=q.get_weekly_trends(db,'a',8)
    assert len(trends)==8
    assert sum(t['complete_observed'] for t in trends)==2
    assert any(t['sets']==0 and t['complete_observed'] for t in trends)

def test_profile_status_settype_and_future_filter(db):
    record(db);record(db,owner='b');record(db,status='ACTIVE');record(db,kind='warmup');record(db,at=NOW+timedelta(days=1))
    assert q.get_data_quality(db,'a')['total_sets']==1

def test_rir_zero_is_present_and_coverage_exact(db):
    record(db,rir=0,rpe=10);record(db,rir=None,rpe=None)
    r=q.get_effort_analysis(db,'a')
    assert r['avg_rir']==0
    assert r['avg_rpe']==10
    assert r['coverage']['with_rir_pct']==50
    assert r['rir_distribution']==[{'rir':0,'count':1}]
    assert r['warning'] is None

def test_decimal_volume_and_reps_exact(db):
    record(db,weight='10.10',reps=3)
    result=q.get_data_quality(db,'a')
    assert result['external_load_volume_kg']==30.3
    assert result['total_reps']==3

def test_e1rm_range_and_single_rep(db):
    assert q._calculate_e1rm(100,1)==100
    assert q._calculate_e1rm(100,6)==120
    assert q._calculate_e1rm(100,15) is None
    assert q._calculate_e1rm(0,8) is None
    eid=record(db,weight='100',reps=15)
    assert q.get_exercise_sessions(db,'a',eid)[0]['e1rm'] is None
    assert q.get_exercise_prs(db,'a',eid)['best_e1rm'] is None

def test_assisted_load_not_treated_as_strength(db):
    eid=record(db,name='Assisted Pull Up',equipment='machine',weight='50',reps=5)
    assert q.get_exercise_prs(db,'a',eid)['best_e1rm'] is None

def test_personal_record_has_date_and_reps(db):
    eid=record(db,weight='30',reps=8)
    prs=q.get_exercise_prs(db,'a',eid)
    assert prs['max_weight']['value']==30
    assert prs['max_weight']['reps']==8
    assert prs['max_weight']['date'].endswith('Z')

def test_plateau_does_not_infer_from_two_sessions(db):
    record(db,days=2);record(db,days=1)
    result=q.get_plateaus(db,'a',8,min_sessions=2)
    assert result['plateaus']==[]
    assert result['assessed_exercises']==0

def test_plateau_observation_requires_time_and_samples(db):
    for days in [20,15,8,1]:record(db,days=days)
    result=q.get_plateaus(db,'a',8)
    assert result['assessed_exercises']==1
    assert result['plateaus'][0]['sessions_count']==4
    assert result['plateaus'][0]['improvement_pct']==0

def test_riyadh_monday_boundary(db):
    record(db,at=datetime(2026,10,25,21,30,tzinfo=timezone.utc))
    result=q.get_weekly_trends(db,'a',1)
    assert result[0]['week']=='2026-10-26'
    assert result[0]['sets']==1
    assert result[0]['partial'] is True

def test_single_set_exercise_is_available(db):
    eid=record(db)
    assert q.get_available_exercises(db,'a')[0]['id']==eid

def test_invalid_historical_row_excluded(db):
    record(db,reps=-1)
    result=q.get_data_quality(db,'a')
    assert result['total_sets']==0
    assert result['excluded_invalid_sets_all_history']==1

def test_no_injury_or_prescription_claims_in_insights(db):
    record(db,rir=0,rpe=10)
    messages=' '.join(str(i) for i in q.get_actionable_insights(db,'a'))
    assert 'injury risk' in messages
    assert 'increase weight' not in messages.lower()
    assert 'ideal' not in messages.lower()

def test_supported_non_warmup_types_are_counted_without_invented_equivalence(db):
    for kind in ['working','dropset','failure','amrap','warmup']:record(db,kind=kind)
    assert q.get_data_quality(db,'a')['total_sets']==4


def test_non_warmup_work_types_are_counted(db):
    for kind in ['working','dropset','failure','amrap','warmup']:
        record(db,kind=kind)
    assert q.get_data_quality(db,'a')['total_sets']==4

def test_exercise_details_obey_selected_calendar_period(db):
    from src.apis.routers.analytics import exercise_deep_dive
    eid=record(db,days=40,weight='100')
    record(db,weight='20')
    result=exercise_deep_dive(eid,days=30,limit=30,weeks=1,db=db,profile_id='a')
    assert result['trend'] is None
    assert result['prs']['max_weight']['value']==20
    assert len(result['sessions'])==1
