import json,hashlib
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
from decimal import Decimal
from src.infrastructure.db.models import CoachingProfileTable,SessionReviewTable,ProductFeedbackTable,SessionTable,PerformedExerciseTable,SetTable,WorkoutPlanTable,PlanExerciseTable,ExerciseTable,TrainingProfileTable,utc_now
from src.services.plan_options import get_options
from src.apis.deps import get_knowledge_provider
VERSION='2026-10-27.guidance1'
WORK_TYPES=('working','dropset','failure','amrap')

def preferences(db,owner):
    row=db.get(CoachingProfileTable,owner)
    return json.loads(row.payload) if row else None

def lock(db):
    connection=db.connection()
    if connection.dialect.name=='sqlite' and not connection.connection.driver_connection.in_transaction:connection.exec_driver_sql('BEGIN IMMEDIATE')

def save_preferences(db,owner,data):
    lock(db)
    profile=db.get(TrainingProfileTable,owner)
    if profile is None:raise ValueError('Complete your basic profile first')
    if data.preferred_days and len(data.preferred_days)!=profile.training_days_per_week:raise ValueError('Selected weekdays must match training days')
    allowed={exercise.movement_pattern for exercise in get_knowledge_provider().exercises()}
    if set(data.avoid_movements)-allowed:raise ValueError('Unknown movement restriction')
    active={r.id for r in db.query(ExerciseTable).filter(ExerciseTable.id.in_(data.disliked_exercise_ids),ExerciseTable.is_active.is_(True)).all()}
    if set(data.disliked_exercise_ids)-active:raise ValueError('Unknown or inactive exercise')
    row=db.get(CoachingProfileTable,owner)
    if row is None:row=CoachingProfileTable(profile_id=owner,payload='{}');db.add(row)
    values=data.model_dump()
    previous=json.loads(row.payload)
    if previous.get('active_program_group_id'):values['active_program_group_id']=previous['active_program_group_id']
    row.payload=json.dumps(values);row.updated_at=utc_now()
    if not data.research_opt_in:db.query(ProductFeedbackTable).filter_by(profile_id=owner).delete(synchronize_session=False)
    db.flush();return data.model_dump()

def context_fingerprint(db,owner):
    choices=preferences(db,owner)
    if choices is None:return None
    context={key:value for key,value in choices.items() if key not in ['research_opt_in','active_program_group_id']}
    profile=db.get(TrainingProfileTable,owner)
    if profile:context['basic']={key:getattr(profile,key) for key in ['experience_level','primary_goal','training_days_per_week','session_duration_minutes']}
    return hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()

def owned_session(db,owner,sid):
    row=db.query(SessionTable).filter_by(id=sid,profile_id=owner).first()
    if row is None:raise LookupError('Session not found')
    return row

def manifest(db,session):
    plan=db.query(WorkoutPlanTable).filter_by(id=session.plan_id,profile_id=session.profile_id).first() if session.plan_id else None
    if plan is None:return []
    alternatives=get_options(db,plan).get('alternatives',{})
    rows=db.query(PlanExerciseTable).filter_by(plan_id=plan.id).order_by(PlanExerciseTable.order_index).all()
    return [dict(exercise_id=r.exercise_id,target_sets=r.target_sets or 1,target_reps=r.target_reps,alternative_id=alternatives.get(r.exercise_id)) for r in rows]

def begin(db,owner,sid):
    connection=db.connection()
    if connection.dialect.name=='sqlite' and not connection.connection.driver_connection.in_transaction:connection.exec_driver_sql('BEGIN IMMEDIATE')
    session=owned_session(db,owner,sid);row=db.get(SessionReviewTable,sid)
    if row is None:
        if session.status!='ACTIVE':raise ValueError('Only active sessions can capture a starting plan')
        row=SessionReviewTable(session_id=sid,profile_id=owner,payload=json.dumps(dict(manifest=manifest(db,session),captured_at_start=not bool(sets_for_session(db,sid)),context_fingerprint=context_fingerprint(db,owner),review=None,method_version=VERSION)))
        db.add(row);db.flush()
    elif row.profile_id!=owner:raise LookupError('Review not found')
    return json.loads(row.payload)

def saved_review(db,owner,sid):
    row=db.query(SessionReviewTable).filter_by(session_id=sid,profile_id=owner).first()
    return json.loads(row.payload) if row else None

def sets_for_session(db,sid):
    rows=db.query(SetTable,PerformedExerciseTable).join(PerformedExerciseTable,SetTable.performed_exercise_id==PerformedExerciseTable.id).filter(PerformedExerciseTable.session_id==sid,PerformedExerciseTable.is_warmup.is_(False),PerformedExerciseTable.is_skipped.is_(False),SetTable.set_type.in_(WORK_TYPES)).all()
    return [(s,p) for s,p in rows if s.weight is not None and Decimal(str(s.weight)).is_finite() and s.weight>=0 and s.reps is not None and s.reps>0]

def progress(db,session,data):
    rows=sets_for_session(db,session.id);result=[]
    for expected in data.get('manifest',[]):
        ids={expected['exercise_id'],expected.get('alternative_id')}
        actual=[s for s,p in rows if p.exercise_id in ids and s.set_type=='working']
        exercise=db.get(ExerciseTable,expected['exercise_id'])
        result.append(dict(**expected,name=exercise.name if exercise else 'Exercise',actual_sets=len(actual),complete=len(actual)>=expected['target_sets'],all_target_reps=bool(actual) and expected['target_reps'] is not None and all(s.reps>=expected['target_reps'] for s in actual),used_alternative=any(p.exercise_id==expected.get('alternative_id') for s,p in rows)))
    volume=sum((Decimal(str(s.weight))*s.reps for s,p in rows),Decimal(0))
    return dict(working_sets=len(rows),reps=sum(s.reps for s,p in rows),volume_kg=float(volume),planned_exercises=result,planned_complete=bool(result) and all(r['complete'] for r in result),unplanned_session=not bool(result))

def store_review(db,owner,sid,review):
    lock(db)
    session=owned_session(db,owner,sid)
    if session.status!='COMPLETED':raise ValueError('Finish the session before reviewing it')
    row=db.get(SessionReviewTable,sid)
    data=saved_review(db,owner,sid) or dict(manifest=manifest(db,session),captured_at_start=False,method_version=VERSION)
    data['review']=review.model_dump();data['reviewed_at']=utc_now().isoformat()
    if row is None:row=SessionReviewTable(session_id=sid,profile_id=owner,payload='{}');db.add(row)
    row.payload=json.dumps(data);row.updated_at=utc_now();db.flush()
    return session_report(db,owner,sid)

def aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def proposals(db,owner,session,data,summary):
    review=data.get('review')
    if not review:return dict(code='review_required',items=[])
    if review['discomfort']:return dict(code='discomfort',items=[])
    latest=db.query(SessionTable).filter(SessionTable.profile_id==owner,SessionTable.plan_id==session.plan_id,SessionTable.status=='COMPLETED',SessionTable.started_at<=utc_now()).order_by(SessionTable.started_at.desc(),SessionTable.id.desc()).first()
    if latest and latest.id!=session.id:return dict(code='historical',items=[])
    if not summary['working_sets']:return dict(code='empty',items=[])
    if summary['unplanned_session']:return dict(code='unplanned',items=[])
    if not summary['planned_complete']:return dict(code='incomplete',reason=review['incomplete_reason'],items=[])
    if review['form_controlled'] is not True or review['effort']=='unsure':return dict(code='technique_or_effort_uncertain',items=[])
    if review['effort']=='hard':return dict(code='hard',items=[])
    if not data.get('captured_at_start'):return dict(code='no_starting_snapshot',items=[])
    if review.get('outside_activity') is not False:return dict(code='outside_activity' if review.get('outside_activity') else 'outside_activity_unknown',items=[])
    choices=preferences(db,owner)
    if choices is None:return dict(code='preferences_required',items=[])
    context=context_fingerprint(db,owner)
    if data.get('context_fingerprint')!=context:return dict(code='preferences_changed',items=[])
    if choices['has_restrictions'] and not choices['avoid_movements']:return dict(code='preferences_changed',items=[])
    known_ids={x['exercise_id'] for x in data['manifest']}|{x.get('alternative_id') for x in data['manifest']}
    if any(p.exercise_id not in known_ids or s.set_type!='working' for s,p in sets_for_session(db,session.id)):return dict(code='extra_work_review',items=[])
    provider=get_knowledge_provider()
    for expected in data['manifest']:
        exercise=db.get(ExerciseTable,expected['exercise_id'])
        if exercise is None:return dict(code='preferences_changed',items=[])
        movement=exercise.movement_pattern;equipment=exercise.equipment or ''
        if exercise.knowledge_variant_id:
            try:
                variant=provider.variant(exercise.knowledge_variant_id);equipment=variant.equipment;movement=provider.exercise(variant.exercise).movement_pattern
            except (KeyError,ValueError):return dict(code='preferences_changed',items=[])
        equipment=equipment.removeprefix('equipment.')
        if equipment not in choices['equipment'] or exercise.id in choices['disliked_exercise_ids'] or movement in choices['avoid_movements'] or (choices['avoid_movements'] and not movement):return dict(code='preferences_changed',items=[])
    if utc_now()-aware(session.started_at)>timedelta(days=14):return dict(code='stale',items=[])
    recent=db.query(SessionTable).filter(SessionTable.profile_id==owner,SessionTable.plan_id==session.plan_id,SessionTable.status=='COMPLETED',SessionTable.started_at<=session.started_at).order_by(SessionTable.started_at.desc(),SessionTable.id.desc()).limit(2).all()
    if len(recent)<2 or len({aware(s.started_at).astimezone(ZoneInfo('Asia/Riyadh')).date() for s in recent})<2:return dict(code='repeat_for_comparison',items=[])
    prior=[(s,saved_review(db,owner,s.id),sets_for_session(db,s.id)) for s in recent]
    profile=db.get(TrainingProfileTable,owner);ceiling=8 if profile and profile.primary_goal=='STRENGTH' else 15
    items=[]
    for expected in data['manifest']:
        plan_exercise=db.query(PlanExerciseTable).filter_by(plan_id=session.plan_id,exercise_id=expected['exercise_id']).first()
        if plan_exercise is None or plan_exercise.target_weight_mode!='LAST_SESSION' or plan_exercise.fixed_reps is not None or plan_exercise.target_reps!=expected['target_reps'] or plan_exercise.target_sets!=expected['target_sets']:continue
        target=expected['target_reps']
        if target is None or target>=ceiling:continue
        evidence=[];weights=[];valid=True
        for s,history,rows in prior:
            if not history or history.get('context_fingerprint')!=context or not history.get('captured_at_start') or utc_now()-aware(s.started_at)>timedelta(days=14):valid=False;break
            feedback=history.get('review') or {}
            if feedback.get('discomfort') or feedback.get('form_controlled') is not True or feedback.get('effort') not in ['easy','appropriate'] or feedback.get('incomplete_reason')!='none' or feedback.get('outside_activity') is not False:valid=False;break
            old=next((x for x in history.get('manifest',[]) if x['exercise_id']==expected['exercise_id']),None)
            if old!=expected:valid=False;break
            actual=[setrow for setrow,performed in rows if performed.exercise_id==expected['exercise_id'] and setrow.set_type=='working']
            alternate_used=any(p.exercise_id==expected.get('alternative_id') for setrow,p in rows)
            if alternate_used or len(actual)!=expected['target_sets'] or any(x.reps<target or x.rir is None or x.rir<2 for x in actual):valid=False;break
            weights.extend(Decimal(str(x.weight)) for x in actual)
            evidence.append(dict(session_id=s.id,reviewed_at=history.get('reviewed_at'),sets=[dict(id=x.id,weight=str(x.weight),reps=x.reps,rir=x.rir) for x in actual]))
        if not valid or len(set(weights))!=1:continue
        row=db.get(ExerciseTable,expected['exercise_id'])
        token=hashlib.sha256(json.dumps(dict(expected=expected,evidence=evidence,version=VERSION),sort_keys=True).encode()).hexdigest()
        items.append(dict(exercise_id=expected['exercise_id'],name=row.name if row else 'Exercise',action='increase_reps',current_reps=target,proposed_reps=target+1,weight_unchanged=True,token=token,evidence_sessions=[x['session_id'] for x in evidence]))
    return dict(code='optional_progression' if items else 'maintain',items=items)

def session_report(db,owner,sid):
    session=owned_session(db,owner,sid)
    data=saved_review(db,owner,sid) or dict(manifest=manifest(db,session),captured_at_start=False,review=None,method_version=VERSION)
    summary=progress(db,session,data)
    return dict(session_id=sid,status=session.status,started_at=aware(session.started_at).isoformat(),review=data.get('review'),snapshot_captured_at_start=data.get('captured_at_start',False),summary=summary,next_step=proposals(db,owner,session,data,summary) if session.status=='COMPLETED' else dict(code='active',items=[]),method_version=VERSION)

def apply_proposal(db,owner,sid,request):
    connection=db.connection()
    if connection.dialect.name=='sqlite' and not connection.connection.driver_connection.in_transaction:connection.exec_driver_sql('BEGIN IMMEDIATE')
    session=owned_session(db,owner,sid)
    if db.query(SessionTable).filter_by(profile_id=owner,plan_id=session.plan_id,status='ACTIVE').first():raise ValueError('Finish the active session before changing its plan')
    report=session_report(db,owner,sid)
    candidate=next((x for x in report['next_step']['items'] if x['exercise_id']==request.exercise_id and x['action']==request.action and x['token']==request.token),None)
    if candidate is None:raise ValueError('Proposal expired or no longer supported by current data')
    session=owned_session(db,owner,sid)
    plan=db.query(WorkoutPlanTable).filter_by(id=session.plan_id,profile_id=owner).first()
    if plan is None:raise LookupError('Plan not found')
    row=db.query(PlanExerciseTable).filter_by(plan_id=plan.id,exercise_id=request.exercise_id).first()
    if row is None:raise LookupError('Exercise not found')
    row.target_reps=candidate['proposed_reps'];db.flush()
    return dict(applied=True,exercise_id=row.exercise_id,target_reps=row.target_reps,weight_changed=False)
