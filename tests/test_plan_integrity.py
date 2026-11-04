import uuid
from datetime import date,datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from tests.test_api import client,db_session,clean_db,sample_exercise
from src.infrastructure.db.models import ExerciseTable,PlanOptionsTable,SessionTable
from src.services.planner_service import PlannerService
from src.services.plan_options import scheduled_today,get_options

def person():
    p=client.post('/api/profiles',json={'name':'Plan QA '+uuid.uuid4().hex[:6]}).json()['id']
    return p,{'X-Profile-Id':p}
def body(exercise,alternate=None,schedules=None):
    return dict(name='QA plan',exercises=[dict(exercise_id=exercise,alternative_exercise_id=alternate,target_sets=2,target_reps=8)],schedules=schedules or [])

def test_weekly_schedule_and_alternative_roundtrip(db_session,sample_exercise):
    owner,h=person();other=ExerciseTable(id=str(uuid.uuid4()),name='QA alternative',primary_muscle='chest',is_active=True);db_session.add(other);db_session.commit()
    payload=body(sample_exercise.id,other.id,[dict(schedule_type='weekly',days_of_week=[0,3])])
    response=client.post('/api/planner/plans',headers=h,json=payload)
    assert response.status_code==200,response.text
    plan=response.json();saved=client.get('/api/planner/plans/'+plan['id'],headers=h).json()
    assert saved['exercises'][0]['alternative_exercise_id']==other.id
    assert saved['schedules']==[dict(schedule_type='weekly',days_of_week=[0,3])]
    service=PlannerService(db_session,profile_id=owner)
    assert service.get_today_plan(date(2026,10,26))['plan'].id==plan['id']
    assert service.get_today_plan(date(2026,10,27)) is None
    payload['name']='Edited QA'
    assert client.put('/api/planner/plans/'+plan['id'],headers=h,json=payload).status_code==200
    again=client.get('/api/planner/plans/'+plan['id'],headers=h).json()
    assert again['schedules']==saved['schedules']
    assert again['exercises'][0]['alternative_exercise_id']==other.id

def test_bad_alternative_rolls_back_entire_plan(db_session,sample_exercise):
    _,h=person()
    response=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id,'missing'))
    assert response.status_code==400
    assert client.get('/api/planner/plans',headers=h).json()==[]

@pytest.mark.parametrize('schedule',[{'schedule_type':'weekly','days_of_week':[]},{'schedule_type':'weekly','days_of_week':[7]},{'schedule_type':'interval','workout_days':None,'rest_days':1},{'schedule_type':'interval','workout_days':0,'rest_days':1}])
def test_invalid_schedule_rejected(db_session,sample_exercise,schedule):
    _,h=person()
    assert client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id,schedules=[schedule])).status_code==422
    assert client.get('/api/planner/plans',headers=h).json()==[]

def test_interval_work_rest_cycle_is_local_calendar_based(db_session,sample_exercise):
    owner,h=person();r=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id,schedules=[dict(schedule_type='interval',workout_days=2,rest_days=1)]))
    assert r.status_code==200,r.text
    service=PlannerService(db_session,profile_id=owner);plan=service.get_plan_by_id(r.json()['id'])
    plan.created_at=datetime(2026,10,25,22,tzinfo=timezone.utc);db_session.commit()
    assert scheduled_today(db_session,plan,date(2026,10,26))
    assert scheduled_today(db_session,plan,date(2026,10,27))
    assert not scheduled_today(db_session,plan,date(2026,10,28))
    assert scheduled_today(db_session,plan,date(2026,10,29))

def test_start_same_plan_resumes_and_other_plan_is_blocked(db_session,sample_exercise):
    owner,h=person();p1=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id)).json()['id'];p2=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id)).json()['id']
    first=client.post('/api/planner/plans/'+p1+'/start',headers=h)
    assert first.status_code==200,first.text
    again=client.post('/api/planner/plans/'+p1+'/start',headers=h)
    assert again.status_code==200,again.text
    assert first.json()['session_id']==again.json()['session_id']
    assert client.post('/api/planner/plans/'+p2+'/start',headers=h).status_code==400
    assert db_session.query(SessionTable).filter_by(profile_id=owner,status='ACTIVE').count()==1

def test_delete_plan_cleans_its_options(db_session,sample_exercise):
    _,h=person();plan=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id)).json()['id']
    assert db_session.get(PlanOptionsTable,plan) is not None
    assert client.delete('/api/planner/plans/'+plan,headers=h).status_code==200
    db_session.expire_all()
    assert db_session.get(PlanOptionsTable,plan) is None

def test_plan_completion_requires_target_working_sets_including_chosen_alternative(db_session,sample_exercise):
    owner,h=person();alternate=ExerciseTable(id=str(uuid.uuid4()),name='Completion alternate',primary_muscle='chest',is_active=True);db_session.add(alternate);db_session.commit()
    p=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id,alternate.id)).json()['id']
    sid=client.post('/api/planner/plans/'+p+'/start',headers=h).json()['session_id']
    for kind in ['warmup','working']:
        assert client.post('/api/workouts/'+sid+'/sets',headers=h,json={'exercise_id':alternate.id,'weight':20,'reps':8,'set_type':kind}).status_code==200
    progress=client.get('/api/planner/sessions/'+sid+'/progress',headers=h)
    assert progress.status_code==200,progress.text
    assert progress.json()['planned_exercises'][0]['is_completed'] is False
    assert client.post('/api/workouts/'+sid+'/sets',headers=h,json={'exercise_id':alternate.id,'weight':20,'reps':8}).status_code==200
    assert client.get('/api/planner/sessions/'+sid+'/progress',headers=h).json()['planned_exercises'][0]['is_completed'] is True

def test_completion_requires_all_working_sets_and_accepts_alternative(db_session,sample_exercise):
    from decimal import Decimal
    from src.infrastructure.db.models import PerformedExerciseTable,SetTable
    owner,h=person()
    alt=ExerciseTable(id=str(uuid.uuid4()),name='Alternate QA',primary_muscle='chest',is_active=True)
    db_session.add(alt);db_session.commit()
    plan=client.post('/api/planner/plans',headers=h,json=body(sample_exercise.id,alt.id)).json()['id']
    sid=client.post('/api/planner/plans/'+plan+'/start',headers=h).json()['session_id']
    pe=PerformedExerciseTable(id=str(uuid.uuid4()),session_id=sid,exercise_id=alt.id,display_order=0)
    db_session.add(pe);db_session.flush()
    def add(kind,order):
        db_session.add(SetTable(id=str(uuid.uuid4()),performed_exercise_id=pe.id,set_order=order,weight=Decimal('20'),reps=8,set_type=kind));db_session.commit()
    service=PlannerService(db_session,profile_id=owner)
    add('warmup',1);add('working',2)
    assert not service.get_session_plan_progress(sid)['planned_exercises'][0]['is_completed']
    add('working',3)
    assert service.get_session_plan_progress(sid)['planned_exercises'][0]['is_completed']
