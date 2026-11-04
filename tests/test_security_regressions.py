import uuid
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from tests.test_api import client, db_session, clean_db, sample_exercise
from src.infrastructure.db.models import SetTable, ClientOperationTable, WorkoutPlanTable, DEFAULT_PROFILE_ID
from src.services.session_service import SessionService
from src.services.generator_service import GeneratorService


def person():
    profile=client.post('/api/profiles',json={'name':'Regression '+uuid.uuid4().hex[:8]}).json()['id']
    return profile, {'X-Profile-Id':profile}

def workout(headers):
    response=client.post('/api/workouts/start',headers=headers,json={})
    assert response.status_code==200
    return response.json()['id']

def add(headers,session,exercise,operation=None):
    payload={'exercise_id':exercise,'weight':20,'reps':8}
    if operation: payload['client_operation_id']=operation
    response=client.post(f'/api/workouts/{session}/sets',headers=headers,json=payload)
    assert response.status_code==200,response.text
    return response.json()['id']

@pytest.mark.parametrize('action',['edit','delete','last','sets'])
def test_cross_profile_set_access_rejected(db_session,sample_exercise,action):
    owner,ah=person(); other,bh=person(); sid=workout(ah)
    setid=add(ah,sid,sample_exercise.id)
    if action=='edit': response=client.patch(f'/api/sets/{setid}',headers=bh,json={'weight':99})
    elif action=='delete': response=client.delete(f'/api/sets/{setid}',headers=bh)
    elif action=='last': response=client.get(f'/api/workouts/{sid}/last-set',headers=bh,params={'exercise_id':sample_exercise.id})
    else:
        assert SessionService(db_session,profile_id=other).get_session_sets(uuid.UUID(sid))==[]
        return
    assert response.status_code in (400,403,404)
    db_session.expire_all()
    assert db_session.get(SetTable,setid).weight==20

def test_operation_replay_requires_owner_and_session(db_session,sample_exercise):
    _,ah=person(); _,bh=person(); alice=workout(ah); bob=workout(bh)
    operation='regression-'+uuid.uuid4().hex
    add(ah,alice,sample_exercise.id,operation)
    response=client.post(f'/api/workouts/{bob}/sets',headers=bh,json={'exercise_id':sample_exercise.id,'weight':20,'reps':8,'client_operation_id':operation})
    assert response.status_code==409

@pytest.mark.parametrize('payload',[{'reps':-2},{'reps':0},{'rpe':99},{'rir':99},{'rir':-1},{'weight':-1}])
def test_invalid_edit_rejected_without_persistence(db_session,sample_exercise,payload):
    owner,headers=person(); sid=workout(headers); setid=add(headers,sid,sample_exercise.id)
    response=client.patch(f'/api/sets/{setid}',headers=headers,json=payload)
    assert response.status_code==422
    db_session.expire_all(); saved=db_session.get(SetTable,setid)
    assert saved.reps==8 and saved.weight==20 and saved.rpe is None and saved.rir is None

def test_service_validates_before_mutating(db_session,sample_exercise):
    owner,headers=person(); sid=workout(headers); setid=add(headers,sid,sample_exercise.id)
    with pytest.raises(ValueError):
        SessionService(db_session,profile_id=owner).update_set(uuid.UUID(setid),reps=-2)
    db_session.commit(); db_session.expire_all()
    assert db_session.get(SetTable,setid).reps==8

def test_generator_uses_requested_profile(db_session,sample_exercise):
    owner,_=person()
    generator=GeneratorService(db_session)
    profile=SimpleNamespace(id=owner,training_days_per_week=3,experience_level="BEGINNER",primary_goal="GENERAL_FITNESS",session_duration_minutes=45)
    with patch.object(generator,'_resolve_template',return_value=SimpleNamespace(name='Regression',id='template.regression')):
        with patch.object(generator,'_select_exercises_for_day',return_value=[(SimpleNamespace(category='compound',movement_pattern='movement.horizontal_push'),None,sample_exercise,2,10)]):
            plans=generator.generate_plan_for_profile(profile)
    assert len(plans)==3
    assert all(plan.profile_id==owner and plan.profile_id!=DEFAULT_PROFILE_ID for plan in plans)

@pytest.mark.parametrize('path',['/api/workouts/not-a-uuid','/api/workouts/not-a-uuid/last-set?exercise_id=bad','/api/workouts/progress?exercise_id=bad'])
def test_invalid_identifiers_return_422(path):
    assert client.get(path).status_code==422

def test_add_set_and_operation_rollback_together(db_session,sample_exercise,monkeypatch):
    from src.apis.routers import sessions
    _,headers=person(); sid=workout(headers)
    original=sessions.SessionLocal
    def broken_session():
        db=original()
        def fail_commit(): raise RuntimeError('Simulated request commit failure')
        db.commit=fail_commit
        return db
    monkeypatch.setattr(sessions,'SessionLocal',broken_session)
    from fastapi.testclient import TestClient
    from src.apis.main import app
    operation='commit-failure-'+uuid.uuid4().hex
    response=TestClient(app,raise_server_exceptions=False).post(f'/api/workouts/{sid}/sets',headers=headers,json={'exercise_id':sample_exercise.id,'weight':20,'reps':8,'client_operation_id':operation})
    assert response.status_code==500
    assert db_session.query(SetTable).count()==0
    assert db_session.query(ClientOperationTable).filter_by(operation_id=operation).first() is None
