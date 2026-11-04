from datetime import datetime,timedelta,timezone
from decimal import Decimal
import uuid,json
import pytest
from tests.test_api import client,db_session,clean_db,sample_exercise
from src.infrastructure.db.models import SessionTable,SessionReviewTable,CoachingProfileTable,ProductFeedbackTable,WorkoutPlanTable,PlanExerciseTable
from src.services import coaching

def person():
    owner=client.post('/api/profiles',json={'name':'Guidance QA '+uuid.uuid4().hex[:6]}).json()['id'];h={'X-Profile-Id':owner}
    r=client.put('/api/profile',headers=h,json=dict(sex='MALE',birth_year=1998,height_cm='178',current_weight_kg='80',experience_level='BEGINNER',training_days_per_week=3,session_duration_minutes=45,primary_goal='GENERAL_FITNESS'))
    assert r.status_code==200,r.text
    return owner,h

def prefs():
    return dict(location='gym',equipment=['machine','cable'],recent_training='new',recent_sessions=0,technique_confidence='learning',has_restrictions=False,avoid_movements=[],disliked_exercise_ids=[],preferred_days=[],research_opt_in=False)

def plan(h,exercise,alternate=None):
    if client.get('/api/coaching/preferences',headers=h).json()['preferences'] is None:
        values=prefs();values['equipment']=['machine','cable','barbell']
        assert client.put('/api/coaching/preferences',headers=h,json=values).status_code==200
    data=dict(name='Guided QA',exercises=[dict(exercise_id=exercise,alternative_exercise_id=alternate,target_sets=2,target_reps=10,target_weight_mode='LAST_SESSION')])
    r=client.post('/api/planner/plans',headers=h,json=data);assert r.status_code==200,r.text
    return r.json()['id']

def session(h,plan_id,exercise,rir=2,effort='appropriate',controlled=True,discomfort=False,outside=False):
    sid=client.post('/api/planner/plans/'+plan_id+'/start',headers=h).json()['session_id']
    from tests.test_api import conn_module
    with conn_module.SessionLocal() as timing:
        row=timing.get(SessionTable,sid)
        completed=timing.query(SessionTable).filter_by(profile_id=row.profile_id,plan_id=plan_id,status='COMPLETED').count()
        row.started_at=datetime.now(timezone.utc)-timedelta(days=3 if completed==0 else 1)
        timing.commit()
    begin=client.post('/api/coaching/sessions/'+sid+'/begin',headers=h);assert begin.status_code==200,begin.text
    for _ in range(2):
        r=client.post('/api/workouts/'+sid+'/sets',headers=h,json=dict(exercise_id=exercise,weight='20',reps=10,rir=rir));assert r.status_code==200,r.text
    assert client.post('/api/workouts/'+sid+'/finish',headers=h).status_code==200
    result=client.put('/api/coaching/sessions/'+sid+'/review',headers=h,json=dict(effort=effort,form_controlled=controlled,discomfort=discomfort,outside_activity=outside,incomplete_reason='none'))
    assert result.status_code==200,result.text
    return sid,result.json()

def test_preferences_private_and_feedback_opt_in_required(db_session):
    a,ha=person();b,hb=person()
    assert client.put('/api/coaching/preferences',headers=ha,json=prefs()).status_code==200
    assert client.get('/api/coaching/preferences',headers=hb).json()['preferences'] is None
    body=dict(stage='setup',understood_next_step=True,needed_external_help=False,friction='none')
    assert client.post('/api/coaching/feedback',headers=ha,json=body).status_code==403
    data=prefs();data['research_opt_in']=True
    assert client.put('/api/coaching/preferences',headers=ha,json=data).status_code==200
    assert client.post('/api/coaching/feedback',headers=ha,json=body).status_code==200
    assert len(client.get('/api/coaching/feedback',headers=ha).json())==1
    assert client.get('/api/coaching/feedback',headers=hb).json()==[]
    assert client.delete('/api/coaching/feedback',headers=hb).json()['deleted']==0
    assert client.put('/api/coaching/preferences',headers=ha,json=prefs()).status_code==200
    assert client.get('/api/coaching/feedback',headers=ha).json()==[]
    assert client.get('/api/coaching/evaluation',headers=ha).status_code==403

@pytest.mark.parametrize('key,value',[('equipment',[]),('equipment',['invented']),('preferred_days',[0,0]),('preferred_days',[7]),('recent_sessions',29),('recent_training','invented'),('profile_id','other')])
def test_invalid_preferences_rejected(db_session,key,value):
    _,h=person();data=prefs();data[key]=value
    assert client.put('/api/coaching/preferences',headers=h,json=data).status_code==422


def test_generation_requires_setup_and_usable_constraints(db_session):
    owner,h=person()
    assert client.post('/api/planner/generate',headers=h).status_code==409
    data=prefs();data['has_restrictions']=True
    assert client.put('/api/coaching/preferences',headers=h,json=data).status_code==200
    assert client.post('/api/planner/generate',headers=h).status_code==400
    assert db_session.query(WorkoutPlanTable).filter_by(profile_id=owner).count()==0

def test_two_comparable_sessions_offer_confirmed_reps_only(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    first,r1=session(h,pid,sample_exercise.id)
    assert r1['next_step']['code']=='repeat_for_comparison'
    second,r2=session(h,pid,sample_exercise.id)
    proposal=r2['next_step']['items'][0]
    assert proposal['proposed_reps']==11 and proposal['weight_unchanged']
    assert db_session.query(PlanExerciseTable).filter_by(plan_id=pid).one().target_reps==10
    request={k:proposal[k] for k in ['exercise_id','action','token']}
    response=client.post('/api/coaching/sessions/'+second+'/apply',headers=h,json=request)
    assert response.status_code==200,response.text
    assert response.json()['target_reps']==11 and not response.json()['weight_changed']
    assert client.post('/api/coaching/sessions/'+second+'/apply',headers=h,json=request).status_code==400
    db_session.expire_all();assert db_session.query(PlanExerciseTable).filter_by(plan_id=pid).one().target_sets==2
    assert client.get('/api/coaching/sessions/'+first,headers=h).json()['next_step']['code']=='historical'

@pytest.mark.parametrize('rir,effort,controlled,discomfort',[(None,'appropriate',True,False),(0,'appropriate',True,False),(2,'hard',True,False),(2,'appropriate',None,False),(2,'appropriate',True,True)])
def test_uncertain_hard_zero_rir_or_discomfort_never_offer_increase(db_session,sample_exercise,rir,effort,controlled,discomfort):
    _,h=person();pid=plan(h,sample_exercise.id)
    session(h,pid,sample_exercise.id)
    _,report=session(h,pid,sample_exercise.id,rir,effort,controlled,discomfort)
    assert report['next_step']['items']==[]


def test_review_and_snapshot_isolation_and_idempotency(db_session,sample_exercise):
    a,ha=person();b,hb=person();pid=plan(ha,sample_exercise.id)
    sid=client.post('/api/planner/plans/'+pid+'/start',headers=ha).json()['session_id']
    first=client.post('/api/coaching/sessions/'+sid+'/begin',headers=ha).json()
    assert client.post('/api/coaching/sessions/'+sid+'/begin',headers=ha).json()==first
    assert db_session.query(SessionReviewTable).filter_by(session_id=sid).count()==1
    assert client.get('/api/coaching/sessions/'+sid,headers=hb).status_code==404
    assert client.post('/api/coaching/sessions/'+sid+'/begin',headers=hb).status_code==404
    assert client.put('/api/coaching/sessions/'+sid+'/review',headers=ha,json=dict(effort='easy',form_controlled=True,discomfort=False,incomplete_reason='none')).status_code==400


def test_starting_targets_survive_plan_edit(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    sid=client.post('/api/planner/plans/'+pid+'/start',headers=h).json()['session_id']
    assert client.post('/api/coaching/sessions/'+sid+'/begin',headers=h).status_code==200
    row=db_session.query(PlanExerciseTable).filter_by(plan_id=pid).one();row.target_sets=4;db_session.commit()
    report=client.get('/api/coaching/sessions/'+sid,headers=h).json()
    assert report['summary']['planned_exercises'][0]['target_sets']==2


def test_old_session_without_start_snapshot_never_proposes_increase(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    sid=client.post('/api/planner/plans/'+pid+'/start',headers=h).json()['session_id']
    db_session.query(SessionReviewTable).filter_by(session_id=sid).delete();db_session.commit()
    client.post('/api/workouts/'+sid+'/sets',headers=h,json=dict(exercise_id=sample_exercise.id,weight='20',reps=10))
    client.post('/api/workouts/'+sid+'/finish',headers=h)
    r=client.put('/api/coaching/sessions/'+sid+'/review',headers=h,json=dict(effort='easy',form_controlled=True,discomfort=False,incomplete_reason='none'))
    assert r.status_code==200,r.text
    assert r.json()['snapshot_captured_at_start'] is False and r.json()['next_step']['items']==[]

def test_same_day_sessions_do_not_trigger_progression(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    first,_=session(h,pid,sample_exercise.id);second,_=session(h,pid,sample_exercise.id)
    recent=db_session.get(SessionTable,second)
    db_session.get(SessionTable,first).started_at=recent.started_at-timedelta(minutes=10);db_session.commit()
    report=client.get('/api/coaching/sessions/'+second,headers=h).json()
    assert report['next_step']['code']=='repeat_for_comparison' and not report['next_step']['items']

def test_active_session_blocks_a_previous_proposal(db_session,sample_exercise):
    _,h=person();pid=plan(h,sample_exercise.id)
    session(h,pid,sample_exercise.id);sid,report=session(h,pid,sample_exercise.id)
    candidate=report['next_step']['items'][0]
    assert client.post('/api/planner/plans/'+pid+'/start',headers=h).status_code==200
    request={key:candidate[key] for key in ['exercise_id','action','token']}
    assert client.post('/api/coaching/sessions/'+sid+'/apply',headers=h,json=request).status_code==400

def test_concurrent_begin_is_one_snapshot(db_session,sample_exercise):
    from concurrent.futures import ThreadPoolExecutor
    owner,h=person();pid=plan(h,sample_exercise.id)
    sid=client.post('/api/workouts/start',headers=h,json={}).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:client.post('/api/coaching/sessions/'+sid+'/begin',headers=h),[0,1]))
    assert all(r.status_code==200 for r in responses)
    assert responses[0].json()==responses[1].json()
    assert db_session.query(SessionReviewTable).filter_by(session_id=sid).count()==1

@pytest.mark.parametrize('outside',[True,None])
def test_outside_training_or_unknown_context_blocks_progression(db_session,sample_exercise,outside):
    _,h=person();pid=plan(h,sample_exercise.id)
    session(h,pid,sample_exercise.id)
    _,report=session(h,pid,sample_exercise.id,outside=outside)
    assert report['next_step']['items']==[]
    assert report['next_step']['code'] in ['outside_activity','outside_activity_unknown']

def test_changed_context_blocks_old_proposal_but_feedback_consent_does_not(db_session,sample_exercise):
    _,h=person();pid=plan(h,sample_exercise.id)
    session(h,pid,sample_exercise.id);sid,report=session(h,pid,sample_exercise.id)
    assert report['next_step']['items']
    values=client.get('/api/coaching/preferences',headers=h).json()['preferences']
    values.pop('active_program_group_id',None);values['research_opt_in']=True
    assert client.put('/api/coaching/preferences',headers=h,json=values).status_code==200
    assert client.get('/api/coaching/sessions/'+sid,headers=h).json()['next_step']['items']
    values['equipment']=['machine']
    assert client.put('/api/coaching/preferences',headers=h,json=values).status_code==200
    report=client.get('/api/coaching/sessions/'+sid,headers=h).json()
    assert report['next_step']['code']=='preferences_changed' and not report['next_step']['items']

def test_late_snapshot_after_work_started_is_not_claimed_as_starting_target(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    sid=str(uuid.uuid4());db_session.add(SessionTable(id=sid,profile_id=owner,plan_id=pid,status='ACTIVE',started_at=datetime.now(timezone.utc)));db_session.commit()
    assert client.post('/api/workouts/'+sid+'/sets',headers=h,json=dict(exercise_id=sample_exercise.id,weight='20',reps=10)).status_code==200
    response=client.post('/api/coaching/sessions/'+sid+'/begin',headers=h)
    assert response.status_code==200,response.text
    assert response.json()['captured_at_start'] is False

def test_planned_start_captures_targets_without_browser_callback(db_session,sample_exercise):
    owner,h=person();pid=plan(h,sample_exercise.id)
    sid=client.post('/api/planner/plans/'+pid+'/start',headers=h).json()['session_id']
    row=db_session.get(SessionReviewTable,sid)
    assert row is not None
    saved=json.loads(row.payload)
    assert saved['captured_at_start'] is True
    assert saved['manifest'][0]['target_sets']==2
