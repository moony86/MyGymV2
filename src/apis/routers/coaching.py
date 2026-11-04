from fastapi import APIRouter,Depends,HTTPException,Query,Request
from src.apis.deps import get_db,get_current_profile_id,get_knowledge_provider
from src.apis.coaching_schemas import Preferences,ReviewInput,FeedbackInput,ProposalInput
from src.services import coaching as service
from src.infrastructure.db.models import SessionTable,ProductFeedbackTable,ExerciseTable,PerformedExerciseTable,SetTable,utc_now
import json
router=APIRouter(prefix='/api/coaching',tags=['coaching'])

def call(function,*args):
    try:return function(*args)
    except LookupError as error:raise HTTPException(404,str(error))
    except ValueError as error:raise HTTPException(400,str(error))

@router.get('/preferences')
def get_preferences(db=Depends(get_db),owner=Depends(get_current_profile_id)):
    return dict(preferences=service.preferences(db,owner),method_version=service.VERSION)

@router.put('/preferences')
def put_preferences(data:Preferences,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    result=call(service.save_preferences,db,owner,data)
    db.commit()
    return result

@router.get('/options')
def options(db=Depends(get_db)):
    provider=get_knowledge_provider()
    return dict(movements=sorted({e.movement_pattern for e in provider.exercises()}),exercises=[dict(id=e.id,name=e.name) for e in db.query(ExerciseTable).filter_by(is_active=True).order_by(ExerciseTable.name).all()])

@router.post('/sessions/{sid}/begin')
def begin(sid:str,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    result=call(service.begin,db,owner,sid)
    db.commit()
    return result

@router.get('/sessions/{sid}')
def report(sid:str,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    return call(service.session_report,db,owner,sid)

@router.put('/sessions/{sid}/review')
def review(sid:str,data:ReviewInput,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    result=call(service.store_review,db,owner,sid,data)
    db.commit()
    return result

@router.post('/sessions/{sid}/apply')
def apply(sid:str,data:ProposalInput,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    result=call(service.apply_proposal,db,owner,sid,data)
    db.commit()
    return result

@router.get('/recent')
def recent(db=Depends(get_db),owner=Depends(get_current_profile_id)):
    sessions=db.query(SessionTable).filter_by(profile_id=owner,status='COMPLETED').order_by(SessionTable.started_at.desc()).limit(12).all()
    return [dict(id=s.id,date=service.aware(s.started_at).isoformat(),reviewed=bool((service.saved_review(db,owner,s.id) or {}).get('review'))) for s in sessions]

@router.get('/exercise/{exercise_id}')
def exercise_guide(exercise_id:str,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    from pathlib import Path
    exercise=db.get(ExerciseTable,exercise_id)
    if exercise is None or not exercise.is_active:raise HTTPException(404,'Exercise not found')
    movement=exercise.movement_pattern;equipment=exercise.equipment
    if exercise.knowledge_variant_id:
        try:
            variant=get_knowledge_provider().variant(exercise.knowledge_variant_id)
            movement=get_knowledge_provider().exercise(variant.exercise).movement_pattern;equipment=variant.equipment
        except (KeyError,ValueError):pass
    rows=db.query(SetTable,SessionTable).join(PerformedExerciseTable,SetTable.performed_exercise_id==PerformedExerciseTable.id).join(SessionTable,SessionTable.id==PerformedExerciseTable.session_id).filter(SessionTable.profile_id==owner,SessionTable.status=='COMPLETED',SessionTable.started_at<utc_now(),PerformedExerciseTable.exercise_id==exercise_id,PerformedExerciseTable.is_warmup.is_(False),PerformedExerciseTable.is_skipped.is_(False),SetTable.set_type=='working').order_by(SessionTable.started_at.desc(),SetTable.set_order.desc()).limit(1).all()
    last=None
    if rows:
        s,session=rows[0]
        if s.weight is not None and __import__('decimal').Decimal(str(s.weight)).is_finite() and s.reps and s.reps>0 and s.weight>=0:last=dict(weight=str(s.weight),reps=s.reps,date=service.aware(session.started_at).isoformat(),stale=(utc_now()-service.aware(session.started_at)).days>=14)
    path=Path(__file__).resolve().parents[3]/'static'/'exercise-media.json'
    media=json.loads(path.read_text()).get(exercise.knowledge_variant_id) if path.exists() else None
    return dict(id=exercise.id,name=exercise.name,movement=movement,equipment=equipment,last=last,media=media)

@router.post('/feedback')
def feedback(data:FeedbackInput,db=Depends(get_db),owner=Depends(get_current_profile_id)):
    service.lock(db)
    preferences=service.preferences(db,owner)
    if not preferences or not preferences.get('research_opt_in'):raise HTTPException(403,'Opt in before submitting product feedback')
    row=ProductFeedbackTable(profile_id=owner,payload=data.model_dump_json());db.add(row);db.flush()
    db.commit()
    return dict(saved=True)

@router.get('/feedback')
def my_feedback(db=Depends(get_db),owner=Depends(get_current_profile_id)):
    rows=db.query(ProductFeedbackTable).filter_by(profile_id=owner).order_by(ProductFeedbackTable.created_at.desc()).limit(50).all()
    return [dict(id=r.id,date=service.aware(r.created_at).isoformat(),**json.loads(r.payload)) for r in rows]

@router.delete('/feedback')
def remove_feedback(db=Depends(get_db),owner=Depends(get_current_profile_id)):
    count=db.query(ProductFeedbackTable).filter_by(profile_id=owner).delete(synchronize_session=False)
    db.commit()
    return dict(deleted=count)

@router.get('/dashboard')
def dashboard(db=Depends(get_db),owner=Depends(get_current_profile_id)):
    from src.infrastructure.db.models import WorkoutPlanTable
    from src.queries.analytics_queries import _monday
    now=utc_now();start=_monday(now).astimezone(__import__('datetime').timezone.utc).replace(tzinfo=None)
    week=db.query(SessionTable).filter(SessionTable.profile_id==owner,SessionTable.status=='COMPLETED',SessionTable.started_at>=start,SessionTable.started_at<=now).all()
    reports=[service.session_report(db,owner,s.id) for s in week]
    plans=db.query(WorkoutPlanTable).filter_by(profile_id=owner,enabled=True).order_by(WorkoutPlanTable.created_at.desc(),WorkoutPlanTable.day_index).all()
    latest=db.query(SessionTable).filter_by(profile_id=owner,status='COMPLETED').order_by(SessionTable.started_at.desc()).first()
    prefs=service.preferences(db,owner) or {}
    active_group=prefs.get('active_program_group_id')
    if active_group:plans=[p for p in plans if p.program_group_id==active_group]
    elif plans and plans[0].program_group_id:plans=[p for p in plans if p.program_group_id==plans[0].program_group_id]
    plans=sorted(plans,key=lambda p:p.day_index or 0)
    active=db.query(SessionTable).filter_by(profile_id=owner,status='ACTIVE').first()
    next_plan=plans[0] if plans else None
    if latest and latest.plan_id:
        current=next((p for p in plans if p.id==latest.plan_id),None)
        if current and current.program_group_id:
            cycle=sorted([p for p in plans if p.program_group_id==current.program_group_id],key=lambda p:p.day_index or 0)
            index=next(i for i,p in enumerate(cycle) if p.id==current.id)
            next_plan=cycle[(index+1)%len(cycle)]
            review=service.saved_review(db,owner,latest.id)
            if review and not service.progress(db,latest,review)['planned_complete']:next_plan=current
    from src.services.plan_options import get_options,scheduled_today,LOCAL
    scheduled=None
    if next_plan and get_options(db,next_plan).get('schedules'):scheduled=scheduled_today(db,next_plan,now.astimezone(LOCAL).date())
    return dict(next_plan_scheduled_today=scheduled,preferences_complete=service.preferences(db,owner) is not None,week_start=start.isoformat()+'Z',completed_sessions=len(week),reviewed_sessions=sum(bool(r['review']) for r in reports),sessions_with_start_snapshot=sum(r['snapshot_captured_at_start'] for r in reports),next_plan=dict(id=next_plan.id,name=next_plan.name) if next_plan else None,last_session=latest.id if latest else None,active_session=dict(id=active.id,plan_id=active.plan_id) if active else None,method='Recorded completed sessions this Riyadh calendar week; next plan continues the most recent program cycle. No automatic make-up volume.')

@router.get('/evaluation')
def evaluation(request:Request,db=Depends(get_db)):
    account=getattr(request.state,'auth',None)
    if not account or not account.get('is_admin'):raise HTTPException(403,'Administrator access required')
    from src.infrastructure.db.models import CoachingProfileTable
    consent={r.profile_id for r in db.query(CoachingProfileTable).all() if json.loads(r.payload).get('research_opt_in')}
    rows=db.query(ProductFeedbackTable).filter(ProductFeedbackTable.profile_id.in_(consent)).order_by(ProductFeedbackTable.created_at.desc()).all()
    latest={}
    for row in rows:
        item=json.loads(row.payload);key=(row.profile_id,item['stage'])
        if key not in latest:latest[key]=item
    summaries=[]
    for stage in ['setup','workout','review']:
        items=[item for (_,s),item in latest.items() if s==stage]
        summaries.append(dict(stage=stage,responses=len(items),understood_next_step=sum(x['understood_next_step'] for x in items),needed_external_help=sum(x['needed_external_help'] for x in items),friction={key:sum(x['friction']==key for x in items) for key in ['none','instructions','load','logging','equipment','other']}))
    return dict(consenting_profiles=len(consent),responding_profiles=len({p for p,s in latest}),stages=summaries,method='Latest voluntary response per profile and stage. Self-reported usability, not evidence of training adaptation or clinical effectiveness.')
